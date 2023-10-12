#!/bin/bash
# Download notetype templates from AnKingMed/AnKing-Note-Types repository

gitdir https://github.com/RisingOrange/AnKing-Note-Types/tree/master/Note%20Types

# gitdir gets confused by %20 (urlencoded whitespace)
rm -r Note%20Types
rm -r src/projekt_anki_notetypes/note_types
mv "Note Types" src/projekt_anki_notetypes/note_types

rm -r src/projekt_anki_notetypes/resources
gitdir https://github.com/AnKingMed/AnKing-Note-Types/tree/master/resources
cp -r resources src/projekt_anki_notetypes/resources
