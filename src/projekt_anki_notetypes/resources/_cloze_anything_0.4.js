/*
Copyright 2019-2021 Matthew Hayes
Copyright 2024 Ankizin
(made compatible with one-by-one, i.e. changed current-cloze to cloze)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

var defaults = {
  showBefore: "all",
  showAfter: "all",
  replaceChar: ".",
  replaceSameLength: "false",
  alwaysShowBlanks: "false",
  blanksFormat: "[{blanks}]",
  hintFormat: "[{hint}]",
  blanksAndHintFormat: "[{blanks}|{hint}]",
  keepRegex: /[!,.:;?—–…]/,
}

var clozeEl = document.getElementById("cloze");
var card = clozeEl.getAttribute("data-card");
var unclozeEls = document.getElementsByClassName("uncloze");

// Controls whether we show other clozes before/after the current cloze.
// Valid values are: all, none, or a positive number
var showBeforeValue = clozeEl.getAttribute("data-cloze-show-before") || defaults.showBefore;
var showAfterValue = clozeEl.getAttribute("data-cloze-show-after") || defaults.showAfter;

// Character used to create blanks that replace content.
var replaceChar = clozeEl.getAttribute("data-cloze-replace-char") || defaults.replaceChar;

// Whether to replace content with blanks having the same number of characters, or a fixed number
// of characters in order to obfuscate the true length.
var replaceSameLength = (clozeEl.getAttribute("data-cloze-replace-same-length") || defaults.replaceSameLength) == "true";

// Whether to always show the blanks.  If true, blanks are always shown, even if there is a hint.
// If false, then blanks are not shown if there is a hint and there are no characters being kept.
var alwaysShowBlanks = (clozeEl.getAttribute("data-cloze-always-show-blanks") || defaults.alwaysShowBlanks) == "true";

// Format of cloze when there is no hint.
var blanksFormat = clozeEl.getAttribute("data-cloze-blanks-format") || defaults.blanksFormat;

// Format of cloze when there is a hint and we aren't showing blanks.
var hintFormat = clozeEl.getAttribute("data-cloze-hint-format") || defaults.hintFormat;

// Format of the cloze when we are showing the blanks and a hint.
var blanksAndHintFormat = clozeEl.getAttribute("data-cloze-blanks-and-hint-format") || defaults.blanksAndHintFormat;

// A regular expression that determines what parts of the text should not be replaced with blanks,
// as if they were surrounded with backticks.
var keepRegex;
if (clozeEl.hasAttribute("data-cloze-keep-regex")) {
  keepRegex = RegExp(clozeEl.getAttribute("data-cloze-keep-regex"));
}
else {
  keepRegex = defaults.keepRegex;
}

// Identify characters in content that will not be replaced with blanks.
var charKeepRegex = /(`[\s\S]+?`)/
var charKeepGlobalRegex = /(`[\s\S]+?`)/g

// Regex used to split on spaces so spaces can be preserved.
var spaceSplit = /\s+/;

// Matches diacritics so we can remove them for length computation purposes.
var combiningDiacriticMarks = /[\u0300-\u036f]/g;

// Wraps the content in a span with given classes so we can apply CSS to it.
function wrap_span(content, classes) {
  return "<span class=\"" + classes + "\">" + content + "</span>";
}

// Replaces content with the replacement character so that result is the same length.
// Spaces are preserved.
function replace_chars_with_blanks(content) {
  // Check if content seems to have HTML.  If so, we'll need to extract text content.
  if (content.indexOf("<") >= 0) {
    content = (new DOMParser).parseFromString(content, "text/html").documentElement.textContent;
  }

  // Decompose so we can remove diacritics to compute an accurate length.  Otherwise
  // diacritics may contibute towards the length, which we don't want.
  content = content.normalize("NFD").replace(combiningDiacriticMarks, "");
  var split = content.split(RegExp("(" + spaceSplit.source + "|" + keepRegex.source + ")"));
  var parts = []
  split.forEach(function(p, i) {
    if (i % 2 == 0) {
      // Replace the non-space characters.
      parts.push(replaceChar.repeat(p.length));
    }
    else {
      // Spaces are returned as is.
      parts.push(p);
    }
  });
  return parts.join("");
}

// Returns the blanks for the given content that serve as a placeholder for it in the cloze.
// Depending on configuration, this could be:
// 1) Blanks with the same number of characters as the content
// 2) Blanks with a fixed number of 3 characters
// 3) A combination of blanks and characters from content that are kept.
function format_blanks(content) {
  var split = content.split(charKeepRegex);
  if (split.length == 1) {
    if (replaceSameLength) {
      return replace_chars_with_blanks(content);
    }
    else {
      return replaceChar.repeat(3)
    }
  }
  else {
    var parts = [];
    split.forEach(function(p, i) {
      if (i % 2 == 0) {
        if (p.length > 0) {
          if (replaceSameLength) {
            parts.push(replace_chars_with_blanks(p));
          }
          else {
            parts.push(replaceChar.repeat(2))
          }
        }
      }
      else {
        // trim the surrounding characters to get the inner content to keep
        parts.push(p.slice(1, p.length - 1));
      }
    });
    return parts.join("")
  }
}

// Performs string replacement of tokens in a {token} format.  For example, {hint} in the format
// will be replaced with the value of the hint key in the dictionary.
function string_format(format, d) {
  return format.replace(/\{([a-z]+)\}/g, function(match, key) {
    return d[key];
  });
}

function strip_keep_chars(content) {
  return content.replace(charKeepGlobalRegex, function(p) {
    return p.slice(1, p.length - 1);
  });
}

// Generates the replacement for the given content and hint.  The result is wrapped in a span
// with the given classes.
function replace_content(content, hint, classes) {
  var contentReplacement = null;
  var showBlanks = alwaysShowBlanks || content.match(charKeepRegex)
  if (showBlanks && hint) {
    contentReplacement = string_format(blanksAndHintFormat, {
      blanks: format_blanks(content),
      hint: hint
    })
  }
  else if (hint) {
    contentReplacement = string_format(hintFormat, {
      hint: hint
    })
  }
  else {
    contentReplacement = string_format(blanksFormat, {
      blanks: format_blanks(content)
    })
  }
  return wrap_span(contentReplacement, classes);
}

function render() {
  var cardMatch = card.match(/[^\d]+(\d+)$/);
  var isBack = !!document.getElementById("back");
  if (cardMatch) {
    var currentClozeNum = parseInt(cardMatch[1]);
    var expContent = clozeEl.innerHTML;

    clozeEl.innerHTML = expContent.replace(/\(\(c(\d+)::([\s\S]+?\)*)\)\)/g,function(match, clozeNum, content) {
      var contentSplit = content.split(/::/)
      var contentHint = null;
      clozeNum = parseInt(clozeNum);
      if (contentSplit.length == 2) {
        contentHint = contentSplit[1];
        content = contentSplit[0]
      }
      var result = null;
      if (isBack) {
        // For the back card we need to strip out the surrounding characters used to mark those
        // we are keeping.  We also wrap in a span in case we want to add styling.
        if (clozeNum == currentClozeNum) {
          result = wrap_span(strip_keep_chars(content), "cloze");
        }
        else {
          result = strip_keep_chars(content);
        }
      }
      else {
        if (clozeNum == currentClozeNum) {
          result = replace_content(content, contentHint, "cloze");
        }
        else if (clozeNum < currentClozeNum) {
          if (showBeforeValue == "all") {
            result = strip_keep_chars(content);
          }
          else if (showBeforeValue.match(/^\d+$/)) {
            var showBeforeNum = parseInt(showBeforeValue);
            if (currentClozeNum - clozeNum <= showBeforeNum) {
              result = strip_keep_chars(content);
            }
            else {
              result = replace_content(content, contentHint, "other-cloze");
            }
          }
          else {
            result = replace_content(content, contentHint, "other-cloze");
          }
        }
        else if (clozeNum > currentClozeNum) {
          if (showAfterValue == "all") {
            result = strip_keep_chars(content);
          }
          else if (showAfterValue.match(/^\d+$/)) {
            var showAfterNum = parseInt(showAfterValue);
            if (clozeNum - currentClozeNum <= showAfterNum) {
              result = strip_keep_chars(content);
            }
            else {
              result = replace_content(content, contentHint, "other-cloze");
            }
          }
          else {
            result = replace_content(content, contentHint, "other-cloze");
          }
        }
        else {
          result = strip_keep_chars(content);
        }
      }

      return result;
    });
  };

  try {
    [].slice.call(unclozeEls).forEach(function(unclozeEl) {
        var unclozeContent = unclozeEl.innerHTML;
        unclozeEl.innerHTML = unclozeContent.replace(/\(\(c(\d+)::([\s\S]+?\)*)\)\)/g,function(match, clozeNum, content) {
          var contentSplit = content.split(/::/)
          if (contentSplit.length == 2) {
            content = contentSplit[0]
          }
          var result = strip_keep_chars(content);
          return result;
        });
      });
  } catch (error) {
    console.error(error);
  }

  // The #cloze element is initially hidden via CSS. Now that rendering has completed,
  // make it visible. Having it initially hidden avoids a potential situation where the
  // clozed markup is temporarily visible before being processed.

  clozeEl.classList.add("show");
}

console.log("Cloze Anything 0.4");

render();
