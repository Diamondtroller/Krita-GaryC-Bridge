# Krita GaryC Bridge


A plugin to make sketch drawings using Krita.

**BEWARE**: This only works with vector data/layers, converting pixel images or using normal paint layers is outside of scope!

## Installation steps:
0. Open Krita,
1. Open Import window by navigate *Tools* > *Scripts* > *Import Python Plugin from Web...* in the top bar,
2. Paste this link to import latest commit https://github.com/Diamondtroller/Krita-GaryC-Bridge/archive/refs/heads/main.zip,
3. Restart Krita.

## Usage
1. Enable docker by navigating *Settings* > *Dockers* > *Krita GaryC Bridge*, **while having a document(could just be empty "New Document")**,
2. Click *Create sketch file* to create document of proper sketch size (you can close the previous document if you don't need it anymore),
3. Click *Load tool options* to **ALMOST** get brush tool ready,
4. In Tool Options (docker) change the setting to be raw,
   
   <img width="262" height="301" alt="attels" src="https://github.com/user-attachments/assets/8425dab3-116c-4396-bed8-e9055bc3f04a" />
5. Draw,
6. Export document to clipboard. This converts **Visible Vector layers** to sketch data and puts it into your clipboard.
7. Paste it into your favourite GaryC client. (For vanilla client you can open console and enter `setData('<clipboard data>')`)
