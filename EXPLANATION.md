# HOW TO USE

Simply change the notetype of your existing cards. Nothing more nothing less.
Do note that some fields have changed names ("Image" is now "Bild", "Date Stamp" is now "Datum"), so make sure to check the field associations in the pop-up dialog.

`Zankiphil - Cloze (Zankiphil - Klinik / Projekt_Anki_Germany)` now becomes `ProjektAnkiCloze`

`Zankiphil - Blickdiagnose (Zankiphil - Klinik / Projekt_Anki_Germany)` now becomes `ProjektAnkiBlickdiagnose`

`Ankiphil - Cloze` now becomes `ProjektAnkiClozePhil`

## How it should look

![How it should look](EXPLANATION_EXAMPLE.png)

# USER CONFIGURATION

## Setup Hint Hotkeys

```
// ##############  HINT REVEAL SHORTCUTS  ##############
// All shortcuts will also open with "H" if using the Hint Hotkeys add-on
var ButtonShortcuts = {
  "Eigene Notizen": "Alt + 1",
  "Prüfungsfragen": "Alt + 2",
  "Klinik": "Alt + 3",
  "Definitionen": "Alt + 4",
  "linkContainer": "Alt + L",
  "Meditricks": "Alt + M",
  "Tags": "Alt + 8",
  "Quelle": "Alt + 9",
  "Note ID": "Alt + 0"
}
var ToggleNextButtonShortcut = "H"
var ToggleAllButtonsShortcut = "J"
// ToggleAllButtonsShortcut currently toggling every button individually
// 1, 2 open; 3, 4 closed -> 1, 2 closed; 3, 4 open
```

## Set which Fields should be shown

set "\<Field\>" to true to show automatically (on flip)

```
// ##############  SHOW HINTS AUTOMATICALLY  ##############
var ButtonAutoReveal = {
  "Eigene Notizen": false,
  "Prüfungsfragen": false,
  "Klinik": false,
  "Definitionen": false,
  "linkContainer": true,
  "Meditricks": false,
  "Tags": false,
  "Quelle": false,
  "Note ID": false
}
var ScrollToButton = false;
```

## Configure the timer

```
// ##############  TIMER CONFIG  ##############
// Timer config (timer length, timer finished message)
var minutes =  0
var seconds = 15
var timeOverMsg = "<span style='color:#CC5B5B'>!!!</span>"
```

## Setup Tag Shortcuts

`tagUniversity` allows to filter the increasingly huge tag list to include only general and university specific tags (e.g. exclude all not Munich-specific tags if you're studying in Munich). Is case-sensitive.

```
// ##############  TAG SHORTCUT  ##############
var toggleTagsShortcut = "C";

// ENTER THE TAG TERM WHICH, WHEN PRESENT, WILL TRIGGER A RED BACKGROUND
var tagID = "XXXYYYZZZ"

// WHETHER THE WHOLE TAG OR ONLY THE LAST PART SHOULD BE SHOWN
var numTagLevelsToShow = 0;

// ENTER THE UNIVERSITY FOR WHICH CURRICULUM SPECIFIC TAGS SHOULD BE SHOWN
var tagUniversity = "XXXYYYZZZ"
```

## Enable Indentation

```
// ##############  INDENTATION  ##############
// Enable experimental heuristic indentation feature
var indentation = true;
```

The heuristic indentation feature was developed to enable notes containing lists to make use of the advantages of lists (i.e. each item is clearly delimited by a bullet point or similar symbol) without having to redo the content of thousands of cards to add HTML `<ul></ul>`-Tags to each and every list.<br>
This is especially relevant for huge collaborative decks with thousands of individual notes (like the German _Ankizin_ deck this notetype was originally developed for).

## Textformatting features

```
// ##############  DIVI FORMAT  ##############
// Enable experimental DIVI medication formatting feature
var formattingDIVI = false;

// ##############  CONFOUNDER FORMAT  ##############
// Enable experimental confounder formatting feature
var formattingConfounders = false;
```

These formatting features are usability features for those who want it.

- `formattingDIVI` changes medication names to the tall-man-letter concept introduced to improve patient safety (e.g. `Fentanyl` -> `fentaNYL`)
- `formattingConfounders` adds an underline to common confounders (e.g. `Hyp_o_kaliämie`)

## Bionic Reading

```
// ############  BIONIC READING  ############
// Enable bionic reading feature (based on AnKing add-on)
var bionicReading = false;
```

This feature implements a Bionic Reading feature based on the AnKing AddOn, with a few tweaks for compatibility.

## Two-Column Layout

```
// ##############  TWO COLUMN  ##############
// Enable experimental two column layout feature
// Will work on Save
var twoColumnLayout = true;
var columnRatio = "1fr 1.5fr"; // variable for grid-template-columns
```

Enable an experimental two column layout for widescreen devices, where the additional info on the back gets it's own column to improve access.

## ONEBYONE-specific settings

```
// ##############  CLOZE ONE BY ONE  ##############
```

### Front Side

```
// Auto flip to back when One by one mode.
var autoflip = true;
```

### Back Side

```
var revealNextShortcut = "N"
var revealNextWordShortcut = "Shift + N"
var toggleAllShortcut = ","

// Enables revealing of next Cloze by simply clicking / tapping anywhere on the card (except the buttons)
var revealAnywhere = true;
```

`revealAnywhere` improves usage on mobile devices allowing you to tap (almost) anywhere on the card to reveal the next cloze.

### Both Sides

```
// INFO ----------------------
// to make a card behave like normal clozes without one-by-one, set:
// selectiveOneByOne = false, minNumberOfClozes = Infinity, alwaysOneByOne = false
// ---------------------------
// THIS NEEDS TO BE SET ON THE BACK AS WELL
// enables selective cloze one-by-one (e.g. only c1 and c3)
// seperate wanted numbers by "," in one-by-one field
var selectiveOneByOne = false;

// THIS NEEDS TO BE SET ON THE BACK AS WELL
// if selective one-by-one is disabled, set this to select a min number of clozes necessary to activate 1b1
// can be set to any number to set lower bound, any falsy value (e.g. 0 or null) disables this setting
var minNumberOfClozes = 2;

// THIS NEEDS TO BE SET ON THE BACK AS WELL
// enables cloze one-by-one even when one-by-one field is empty
// minNumberOfClozes is still considered in this case
// overridden in importance by selectiveOneByOne
var alwaysOneByOne = true;
// ----------------------------
```

This right here needs some more explaining:<br>
The OneByOne Notetype is incredibly configurable, so YOU can learn YOUR way.

## Now what do the separate settings do?

### `selectiveOneByOne`

To overcome one issue of the AnKing OneByOne notetype, I introduce to you _Selective OneByOne_. This means, that you can select for each card individually which cloze numbers should be treated as OneByOne, and which shouldn't. There is a sequence of diagnostic procedures that you can't seem to keep in your head? Reveal each step after the other! Another sequence of diagnostic procedures you know by heart and can do them blindfolded? Reveal all of them at once! You can also use this, when the different partial answers act as clues towards each other, so you want to mitigate learning "A then B then C", but instead want to learn "A and B and C".<br>
With _Selective OneByOne_ you are in control!

### `minNumberOfClozes`

You want to take advantage of the benefits of OneByOne, but don't want to select the Clozes for each card separately? No problemo, just disable `selectiveOneByOne`, and set `minNumberOfClozes` to your preferred number.<br>
Want every Cloze with more than 2 Elements to act as OneByOne? Set `minNumberOfClozes = 2`. Want every Cloze with more than 10 Elements to act as OneByOne? Set `minNumberOfClozes = 10`. The choice is yours.<br>
However, if you don't want OneByOne to be the absolute default for every card you learn, don't forget to disable `alwaysOneByOne`.

### `alwaysOneByOne`

`alwaysOneByOne = True` enables OneByOne for each and every card using this notetype. `alwaysOneByOne = False` enables OneByOne only for the cards with a non-empty OneByOne field.

## Why the differentiation?

It's all about customization. For deck creators wanting to use this notetype, the following default setup might be the most useful:

```
var selectiveOneByOne = false;
var minNumberOfClozes = 2;
var alwaysOneByOne = true;
```

This way you can simply change the notetypes of all your cards to this new one, without worrying about having to individually set selective OneByOne cues.

## Use Case Examples

### All cards where cloze $x$ has more than 3 occurences, should use OneByOne

**This is the standard setting!**

```
var selectiveOneByOne = false;
var minNumberOfClozes = 3;
var alwaysOneByOne = true;
```

### Only specific cards where cloze $x$ has more than 2 occurences, should use OneByOne

These cards need something in the OneByOne field (any string / letter / number will do)

```
var selectiveOneByOne = false;
var minNumberOfClozes = 2;
var alwaysOneByOne = false;
```

### All cards where should use OneByOne, but only for specific clozes $x$

These cards need the specific cloze numbers in the OneByOne field (format `<number><comma><space>`: `1, 3, 5`)

```
var selectiveOneByOne = true;
var minNumberOfClozes = 2; # doesn't matter
var alwaysOneByOne = true;
```

### Only specific cards should use OneByOne, but only for specific clozes $x$

These cards need the specific cloze numbers in the OneByOne field (format `<number><comma><space>`: `1, 3, 5`)

```
var selectiveOneByOne = true;
var minNumberOfClozes = 2; # doesn't matter
var alwaysOneByOne = false;
```

# Specific fields

## `weitere Links`

The `weitere Links` field allows one to add an theoretically unlimited number of additional weblinks to other resources without a dedicated Button (as Amboss & Thieme _via medici_ have).

Please use the [Add Hyperlink](https://ankiweb.net/shared/info/318752047) addon to insert the links, as they need to follow the following standard HTML structure:

```
<a href=" $weblink "> $weblink-title </a>
```

The added links get their own buttons generated automatically.
