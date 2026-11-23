import datetime

from anki.errors import AnkiError
from anki.scheduler import FilteredDeckForUpdate
from anki.utils import int_time
from aqt import gui_hooks, mw
from aqt.browser import SearchContext
from aqt.errors import show_exception
from aqt.operations import CollectionOp
from aqt.qt import QTimer
from aqt.reviewer import RefreshNeeded
from aqt.utils import tooltip

from ..constants import ADDON_DIR_NAME
from ..home.dashboard import deck_browser_ankizin_hk, on_webview_js_message
from ..onboarding.maintenance import run_startup_maintenance
from ..onboarding.wizard import maybe_prompt_onboarding_on_startup
from ..study_hub.smart_decks import SmartMaintenanceResult, maintain_smart_decks
from .browser import filtered_deck_hk
from .lernplan_decks import (
    DeckResult,
    LerntagSettings,
    effective_today,
    get_kreuzen_tage,
    get_lerntag_list,
    get_lerntag_order,
    get_lerntag_topics,
    kreuzen_count,
    next_lerntag,
    rebuild_lernplan_decks,
    update_past_days,
)
from .lernplan_progress import deck_browser_progress_hk
from .lernplan_schedule import is_lernplan_day, parse_dates
from .utils import report_result
from .menu import get_rebuild_config

SYNC_TIMEOUT_MS = 120_000  # fallback if no sync attempt concludes


def run_today_setup():
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if conf is not None and "lernplan" in conf:
        last_updated = conf["lernplan"].get("last_updated", None)

        if last_updated is None:
            # No last_updated date available, so we assume the setup should be run
            return True

        # Check if the rebuild hooks should be run right now
        last_updated = datetime.datetime.fromisoformat(last_updated).date()
        today = effective_today(mw.col)

        if last_updated < today:
            return True
        else:
            return False  # Last updated date is today or in the future

    # No config available, so we assume the setup shouldn't be run
    return False


# The startup steps run one after the other as background ops (the UI stays responsive).
# Every step decides on the main thread, builds in a CollectionOp and then calls `then`.
# Later steps read the config the earlier ones write, so they must wait for the success callback.
# One progress dialog (modal, UI keeps repainting) covers the whole chain, so there is no gap
# between the steps in which the user could start something; it only shows if the chain takes >0.6s.
_running = False


def _finish() -> None:
    global _running
    _running = False
    mw.progress.finish()


def _fail(exception: Exception) -> None:
    """A failed step stops the chain and persists nothing, so the next start retries."""
    _finish()
    show_exception(parent=mw, exception=exception)


def _rebuild_lernplan_decks(conf, then, **kwargs):
    """Rebuild the decks for conf['lernplan'] in the background, then persist conf and go on."""
    lernplan_conf = conf["lernplan"]
    settings = LerntagSettings.from_conf(lernplan_conf)
    past_days = lernplan_conf.get("past_days", [])

    def done(result: DeckResult) -> None:
        # only persist after the decks exist
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
        report_result(result, silent=True)
        then()

    CollectionOp(
        mw, lambda col: rebuild_lernplan_decks(col, settings, past_days=past_days, **kwargs)
    ).success(done).failure(_fail).run_in_background()


def lernplan_auto_create(then):
    """Auto-create lernplan decks based on schedule and configuration"""
    # Get configuration
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if not run_today_setup():
        return then()

    lernplan_conf = conf["lernplan"]

    # Validate prerequisites
    if not lernplan_conf.get("autocreate", False):
        return then()

    # Check if today is a scheduled lernplan day
    if not is_lernplan_day(
        effective_today(mw.col),
        lernplan_conf["wochentage"],
        parse_dates(lernplan_conf.get("extra_days")),
        parse_dates(lernplan_conf.get("skip_days")),
    ):
        return then()  # Today is not a lernplan day (free weekday or skipped)

    # Calculate and validate next lerntag (in the user's order, skipping finished days)
    current_lerntag = lernplan_conf.get("lerntag", "001")
    lerntage = get_lerntag_list(mw.col)
    new_lerntag = next_lerntag(
        get_lerntag_order(lerntage, lernplan_conf),
        current_lerntag,
        lernplan_conf.get("past_days", []),
    )
    if new_lerntag is None:
        return then()  # Lernplan is finished

    count = kreuzen_count(lernplan_conf)
    if new_lerntag in get_kreuzen_tage(lerntage, count):
        tooltip(f"📚 Heute kreuzen: {get_lerntag_topics(lerntage, count)[new_lerntag]}", period=8000)

    # Record the day we are leaving in the history (past_days)
    update_past_days(current_lerntag, new_lerntag, conf)

    lernplan_conf["lerntag"] = new_lerntag
    due = lernplan_conf.get("autocreate_due", False)
    today = effective_today(mw.col).isoformat()
    lernplan_conf["last_updated"] = today
    if due:
        lernplan_conf["last_due_updated"] = today

    _rebuild_lernplan_decks(
        conf,
        then,
        cleanup=True,
        previous=lernplan_conf.get("autocreate_previous", False),
        due=due,
    )


def lernplan_due_deck_auto_create(then):
    """Create due deck daily, independent of lernplan schedule"""
    # Get configuration
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if conf is None or "lernplan" not in conf:
        return then()

    lernplan_conf = conf["lernplan"]

    # Validate prerequisites
    if not lernplan_conf.get("autocreate_due", False):
        return then()
    if not lernplan_conf.get("autocreate", False):
        return then()

    # Check if update is needed today
    last_due_updated = lernplan_conf.get("last_due_updated", None)
    today = effective_today(mw.col)

    if last_due_updated is not None:
        last_due_date = datetime.datetime.fromisoformat(last_due_updated).date()
        if last_due_date >= today:
            return then()  # Already updated today

    # Current lerntag stays as it is, only the due deck is refreshed
    lernplan_conf["last_due_updated"] = today.isoformat()
    _rebuild_lernplan_decks(conf, then, current=False, due=True)


def is_ankizin_deck(deck: FilteredDeckForUpdate) -> bool:
    """Lernplan decks and decks made from Ankizin tags all search for an #Ankizin tag."""
    return any("#ankizin" in term.search.lower() for term in deck.config.search_terms)


def rebuild_filtered_decks(col, enabled: bool, only_ankizin: bool) -> DeckResult:
    """Worker thread: rebuild the filtered decks as ONE undoable step (collection calls only)."""
    target = col.add_custom_undo_entry("Auswahlstapel neu aufbauen")
    result = DeckResult()
    for deck in col.decks.all_names_and_ids():
        if not col.decks.is_filtered(deck.id):
            continue
        try:
            if "REBUILD" in deck.name:  # always rebuilt
                col.sched.rebuild_filtered_deck(deck.id)
            elif enabled:
                fdeck = col.sched.get_or_create_filtered_deck(deck_id=deck.id)
                if only_ankizin and not is_ankizin_deck(fdeck):
                    continue
                search = fdeck.config.search_terms[0]
                if "is:new" in search.search or "is:due" in search.search:  # already finetuned
                    col.sched.rebuild_filtered_deck(deck.id)
                else:
                    search.search = f"({search.search}) (is:new or is:due)"
                    fdeck.allow_empty = True  # get_or_create_filtered_deck always returns False here
                    col.sched.add_or_update_filtered_deck(fdeck)
        except AnkiError as e:  # one broken search must not stop the other decks
            result.failed.append((deck.name, str(e)))
    result.changes = col.merge_undo_entries(target)
    return result


def auto_rebuild_filtered_decks(then):
    # Runs after the lernplan decks are created and also adds "(is:new or is:due)"
    # to their searches (unless the deck name contains REBUILD) - this is intended.
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)

    # no configuration available, skipping auto rebuild of filtered decks
    if conf is None:
        return then()

    # Check if the setup should be run today
    last_rebuild = conf.get("last_rebuild", None)
    if last_rebuild is not None:
        if datetime.datetime.fromisoformat(last_rebuild).date() >= effective_today(mw.col):
            return then()

    config = get_rebuild_config()
    enabled = config["autoRebuildDecksOnStartup"]
    only_ankizin = config["autoRebuildOnlyAnkizinDecks"]
    print("Auto rebuild filtered decks (Ankizin):", enabled, "only Ankizin decks:", only_ankizin)

    def done(result: DeckResult) -> None:
        # Anki's day (respects rollover), same as everywhere else
        conf["last_rebuild"] = effective_today(mw.col).isoformat()
        mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
        report_result(result, silent=True)
        then()

    CollectionOp(
        mw, lambda col: rebuild_filtered_decks(col, enabled, only_ankizin)
    ).success(done).failure(_fail).run_in_background()


# There is a bug in the Amboss website query that accidentally excludes Ankizin notes. We fix it for them here :)
def browser_search_hk(context: SearchContext):  # type: ignore
    search_term = context.search

    target_string = "note:Ankiphil*"
    high_yield_target = "tag:*!High-Yield"
    high_yield_tags = [
        "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::01-*",
        "#Ankizin_*::!MARKIERE_DIESE_KARTEN::M2_IMPP-Relevanz_(yield)::02-*",
    ]

    has_ankiphil = target_string in search_term
    has_amboss_field = "AMBOSS*:" in search_term
    has_ankizin = "note:ProjektAnki*" in search_term

    if has_ankiphil and has_amboss_field and not has_ankizin:
        replacement_string = "(note:Ankiphil* OR note:ProjektAnki*)"

        modified_search_term = search_term.replace(
            target_string, replacement_string, 1
        )
        search_term = modified_search_term

        if high_yield_target in search_term:
            high_yield_search = " OR ".join(
                [f'"tag:{tag}"' for tag in high_yield_tags]
            )
            search_term = search_term.replace(
                high_yield_target, f"({high_yield_search})", 1
            )

        context.search = search_term


def _run_smart_deck_maintenance(then):
    """Rebuild daily Smart Decks once per day and auto-clean finished one-shot Smart Decks."""
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME)
    if not conf or not conf.get("smart_decks"):
        return then()

    last_rebuild = conf.get("last_rebuild", None)
    should_rebuild_daily = True
    if last_rebuild is not None:
        try:
            if datetime.datetime.fromisoformat(last_rebuild).date() >= effective_today(mw.col):
                should_rebuild_daily = False
        except ValueError:
            pass
    rebuild_enabled = bool(get_rebuild_config().get("autoRebuildDecksOnStartup", True))
    rebuild_daily = should_rebuild_daily and rebuild_enabled

    def op(col):
        res = maintain_smart_decks(col, conf, rebuild_daily=rebuild_daily)
        return res

    def done(res: SmartMaintenanceResult) -> None:
        if res.changed_conf:
            mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
        if res.auto_cleaned:
            tooltip(
                "Smart-Stapel fertig gelernt & aufgeräumt: " + ", ".join(res.auto_cleaned),
                parent=mw,
                period=4500,
            )
        then()

    CollectionOp(mw, op).success(done).failure(_fail).run_in_background()


def _on_state_did_change(new_state: str, old_state: str) -> None:
    """When returning from a study session to the Deck Browser, auto-clean empty one-shot Smart Decks."""
    if new_state != "deckBrowser" or old_state not in ("review", "overview"):
        return
    if not mw or not getattr(mw, "col", None):
        return
    conf = mw.addonManager.getConfig(ADDON_DIR_NAME) or {}
    smart_conf = conf.get("smart_decks") or {}
    if not any((meta or {}).get("lifecycle") == "auto_clean" for meta in smart_conf.values()):
        return

    def op(col):
        return maintain_smart_decks(col, conf, rebuild_daily=False)

    def done(res: SmartMaintenanceResult) -> None:
        if res.changed_conf:
            mw.addonManager.writeConfig(ADDON_DIR_NAME, conf)
        if res.auto_cleaned:
            tooltip(
                "Smart-Stapel fertig gelernt & aufgeräumt: " + ", ".join(res.auto_cleaned),
                parent=mw,
                period=4500,
            )
            if mw.state == "deckBrowser":
                mw.deckBrowser.refresh()

    CollectionOp(mw, op).success(done).run_in_background()


def reload_data_hk():
    global _running
    if _running:  # called from sync, timeout and day change; the running chain covers today
        return
    _running = True
    mw.progress.start(label="Ankizin-Stapel werden aktualisiert...")
    run_startup_maintenance(
        lambda: lernplan_auto_create(
            lambda: lernplan_due_deck_auto_create(
                lambda: _run_smart_deck_maintenance(lambda: auto_rebuild_filtered_decks(_finish))
            )
        )
    )


def profile_loaded_hk():
    if mw.pm.auto_syncing_enabled() and mw.pm.sync_auth() and not mw.safeMode:

        def on_sync_finished_hk():
            # run reload_data AFTER sync is finished
            reload_data_hk()

            try:
                gui_hooks.sync_did_finish.remove(on_sync_finished_hk)
            except ValueError:
                pass  # Hook wasn't registered, ignore

        gui_hooks.sync_did_finish.append(on_sync_finished_hk)
        # no sync attempt concluded (e.g. pending login): run anyway; reload_data is a no-op when it already ran today
        mw.progress.timer(SYNC_TIMEOUT_MS, on_sync_finished_hk, repeat=False, parent=mw)
    else:
        # No auto-sync or not configured for sync, run immediately
        reload_data_hk()

    # Hook alternative for Anki 25.02 and older support
    # TODO Remove in a year or so when we can expect Anki 25.06+ users only
    if not hasattr(gui_hooks, "day_did_change"):
        last_day_cutoff = mw.col.sched.day_cutoff

        def refresh_reviewer_on_day_rollover_change():
            nonlocal last_day_cutoff
            current_cutoff = mw.col.sched.day_cutoff
            if last_day_cutoff != current_cutoff:
                last_day_cutoff = current_cutoff
                if mw.state == "review":
                    mw.reviewer._refresh_needed = RefreshNeeded.QUEUES
                    mw.reviewer.refresh_if_needed()
                reload_data_hk()

            # schedule another check
            secs_until_cutoff = current_cutoff - int_time()
            mw._reviewer_refresh_timer = mw.progress.timer(  # type: ignore
                secs_until_cutoff * 1000,
                refresh_reviewer_on_day_rollover_change,
                repeat=False,
                parent=mw,
            )

        refresh_reviewer_on_day_rollover_change()

    QTimer.singleShot(1800, maybe_prompt_onboarding_on_startup)


SHOW_IO_FIELD_JS = """
        (function () {
          // Only set up the observer once per page load
          if (window.myOcclusionObserver) return;

          function showIOfield() {
            document.querySelectorAll('.field-container').forEach(el => {
              el.classList.remove('hide');
            });
          }

          // Run once on initial load
          showIOfield();

          // Set up MutationObserver
          const observer = new MutationObserver((mutations) => {
            // Check if relevant nodes have been added or changed
            for (const mutation of mutations) {
              if (mutation.type === "childList") {
                showIOfield();
              }
            }
          });

          // Start observing the editor root node
          const editorRoot = document.querySelector('.note-editor');
          if (editorRoot) {
            observer.observe(editorRoot, {
              childList: true,
              subtree: false,  // Only observe direct children
              attributes: false,  // Only observe direct children,
            });
            window.myOcclusionObserver = observer;
          }
        })();
        """


def show_io_field_in_editor_hk(editor) -> None:
    """Show the IO field in the editor of ProjektAnkiIO notes (legacy and new editor)."""
    note = getattr(editor, "note", None)
    if note is None and getattr(editor, "nid", None):  # the new editor only knows the id
        note = mw.col.get_note(editor.nid)
    if note and note.note_type()["name"].startswith("ProjektAnkiIO"):
        editor.web.eval(SHOW_IO_FIELD_JS)


def hooks_init():
    gui_hooks.profile_did_open.append(profile_loaded_hk)
    gui_hooks.browser_sidebar_will_show_context_menu.append(filtered_deck_hk)
    gui_hooks.browser_will_search.append(browser_search_hk)
    gui_hooks.deck_browser_will_render_content.append(deck_browser_ankizin_hk)
    gui_hooks.deck_browser_will_render_content.append(deck_browser_progress_hk)
    gui_hooks.webview_did_receive_js_message.append(on_webview_js_message)
    if hasattr(gui_hooks, "state_did_change"):
        gui_hooks.state_did_change.append(_on_state_did_change)
    # for Anki 25.06 and later, we can use the new hook
    if hasattr(gui_hooks, "day_did_change"):
        gui_hooks.day_did_change.append(reload_data_hk)

    gui_hooks.editor_did_load_note.append(show_io_field_in_editor_hk)