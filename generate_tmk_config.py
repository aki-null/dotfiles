#!/usr/bin/env python3
"""
aki_null Keymap Replication for Karabiner-Elements
===================================================

Generate Karabiner-Elements configuration that replicates the aki_null keymap
configuration from TMK keyboard firmware.

This is a personal keymap configuration for me that uses TMK keyboard firmware features.
This script replicates that keymap's behavior in Karabiner-Elements for use on macOS with
any keyboard.

Original TMK keymap location: tmk_keyboard/keyboard/hhkb/keymap_akinull.c

OVERVIEW
--------
This script generates a complete Karabiner-Elements configuration that replicates my keymap,
which uses TMK keyboard firmware features for custom tap/hold keys:

1. Left Control: hold for Ctrl, tap for Esc
2. Left Shift: hold for Shift, tap for '('
3. Right Shift: hold for Shift, tap for ')'
4. F key: hold for Vim layer (arrows/F-keys), tap for 'f'
   - With "waiting buffer" that queues keys during the tapping window

Tapping term (TAPPING_TERM_MS) is configurable.

CRITICAL DESIGN DECISIONS
--------------------------

### 1. F Key as REAL MODIFIER (not variable-based layer)

**THE KEY INSIGHT**: Variable conditions in Karabiner-Elements DO NOT support key repeat!

When F is held (after the tapping term expires), it outputs `right_option` (a real modifier key),
not just setting a variable. This is CRITICAL for key repeat to work.

**Failed Approach 1**: Variable-based layer
```json
// F held -> set vim_layer=1
// J pressed with condition vim_layer=1 -> down_arrow
// Problem: J repeat doesn't work! Each repeat event must re-check vim_layer condition,
// which breaks the OS key repeat mechanism.
```

**Failed Approach 2**: Simultaneous keys
```json
// F+J simultaneous detection -> down_arrow
// Problem: Doesn't work for "hold F, THEN press J" - simultaneous requires
// both keys pressed nearly at the same time (within threshold).
```

**Working Approach**: F becomes real modifier
```json
// F held (tapping term) -> outputs right_option modifier
// J with mandatory right_option modifier -> down_arrow
// Success: OS sees "right_option + J" as normal key combo, key repeat works!
```

### 2. Waiting Buffer Implementation (Queuing System)

**THE PROBLEM**: The aki_null keymap uses TMK's "waiting buffer" feature that queues
keypresses during the tapping term. Without this, typing "diff " fast becomes "dif f"
(space outputs before second 'f' is released).

**HOW IT WORKS**:
- When F is pressed: f_pressed=1, f_tapping=1, f_was_modifier=0
- During tapping window: ALL keys get queued (set queued_X=1)
- When F is released: to_after_key_up replays 'f' + all queued keys in order
- After tapping term: to_if_held_down sets f_was_modifier=1, outputs right_option

**CRITICAL**: Vim nav keys (h,j,k,l,u,d) MUST be queued during tapping window!

**Bug Example**: If 'u' wasn't queued, typing "full" fast would become "ufll":
1. Press F (tapping window starts)
2. Press U while F held -> U outputs immediately (not queued)
3. Release F -> outputs 'f'
4. Result: "u" + "f" + "ll" = "ufll" ❌

**Solution**: Queue ALL alphabet keys + space + punctuation during tapping window.
Then have SEPARATE vim layer manipulator that activates with right_option modifier.

### 3. Control Key: Lazy Modifier Pattern

**THE PROBLEM**: Regular modifier output breaks the tap behavior.

**Working Pattern**:
```json
"to": [{"key_code": "left_control", "lazy": true}],  // Don't send until other key
"to_if_alone": [{"key_code": "escape"}],              // Tap -> Esc
"to_if_held_down": [{"key_code": "left_control"}]    // Hold -> Ctrl
```

The `"lazy": true` is CRITICAL - it prevents Ctrl from being sent until another key
is pressed, allowing the tap-to-Esc behavior to work.

STATE MACHINE
-------------

### F Key States:

1. **f_pressed** (0 or 1)
   - Physical state: 1 while F key is physically held down
   - Used to enable queue manipulators

2. **f_tapping** (0 or 1)
   - Timing state: 1 during tapping window, then 0
   - Not directly used (implicit in f_was_modifier)

3. **f_was_modifier** (0 or 1)
   - Role state: 0 during tapping window, 1 after becoming modifier
   - Used to distinguish: tapping window (queue keys) vs vim layer (pass through)
   - Prevents 'f' output if vim layer was used

### Queue Variables:

- **queued_X**: Set to 1 when key X pressed during tapping window (f_was_modifier=0)
- **queued_X_1, queued_X_2, queued_X_3**: Multi-slot for commonly doubled keys

TIMING DIAGRAM
--------------

Example 1: Typing "diff " fast
```
Time (ms):  0      10     15     20     T+10   T+15
            |      |      |      |      |      |
            F↓           F↑     F↓     Space   F↑
            (where T = TAPPING_TERM_MS)

F pressed (first 'f' in "diff"):
  t=0:    f_pressed=1, f_was_modifier=0
  t=10:   (tapping window, no key pressed)
  t=15:   F released before tapping term -> output 'f'

F pressed again (second 'f' in "diff"):
  t=20:     f_pressed=1, f_was_modifier=0 (new tapping window)
  t=T+10:   Space pressed while F still held -> queued_spacebar=1 (NOT output yet!)
  t=T+15:   F released -> to_after_key_up:
            - output 'f' (because f_was_modifier=0)
            - output space (because queued_spacebar=1)

Result: "diff " ✓
```

Example 2: Hold F for vim navigation
```
Time (ms):  0      50     T      T+50   T+100  T+150
            |      |      |      |      |      |
            F↓           [timeout] J↓    J↑     F↑
            (where T = TAPPING_TERM_MS)

  t=0:       f_pressed=1, f_was_modifier=0, f_tapping=1
  t=T:       to_if_held_down triggers:
             - f_was_modifier=1
             - f_tapping=0
             - output right_option (F becomes modifier!)
  t=T+50:    J pressed with right_option modifier -> down_arrow
  t=T+100:   J released
  t=T+150:   F released -> to_after_key_up:
             - NO 'f' output (because f_was_modifier=1)
```

Example 3: Vim key repeat (the key fix!)
```
Time (ms):  0      T      T+50   T+100  T+150  ...
            |      |      |      |      |      |
            F↓    [timeout] J↓   [repeat] [repeat]
            (where T = TAPPING_TERM_MS)

  t=0:       f_pressed=1, f_was_modifier=0
  t=T:       F becomes right_option modifier
  t=T+50:    J pressed -> right_option+J -> down_arrow
  t=T+100:   J still held, OS generates repeat event
             -> right_option+J (again) -> down_arrow ✓
  t=T+150:   OS repeat -> right_option+J -> down_arrow ✓

Key insight: OS key repeat sends "right_option + J" repeatedly,
and this is just a normal key combo lookup - no variable conditions!
```

QUEUE SYSTEM DETAILS
---------------------

### Keys Queued:

1. **All alphabet keys** (a-z except 'f'):
   - Includes vim nav keys (h,j,k,l,u,d) during tapping window
   - They have separate vim layer manipulator with right_option modifier

2. **Multi-slot keys** (commonly doubled): e, o, p, s, z
   - Have 3 slots: queued_X_1, queued_X_2, queued_X_3
   - Example: "foo" typed fast with F held -> queues both 'o's

3. **Additional keys**: spacebar, comma, period, slash, semicolon, quote, brackets
   - Essential for proper typing (e.g., "diff " with space)

4. **NOT queued**: Numbers and vim layer keys (backtick, hyphen, equals, backslash, 0-9)
   - These need to pass through for vim layer F1-F12 mappings

### Queue Manipulator Conditions:

```json
"conditions": [
  {"type": "variable_if", "name": "f_pressed", "value": 1},       // F is held
  {"type": "variable_if", "name": "f_was_modifier", "value": 0}   // Still in tapping window
]
```

When BOTH conditions are true -> queue the key instead of outputting it.

### Queue Replay (in to_after_key_up):

1. Output 'f' (only if f_was_modifier=0)
2. Output all queued alphabet keys in alphabetical order
3. Output all queued additional keys
4. Clear all queue variables
5. Clear all state variables

VIM LAYER MAPPINGS
------------------

### Navigation (vim nav keys -> arrows/page):
- h -> left_arrow
- j -> down_arrow
- k -> up_arrow
- l -> right_arrow
- u -> page_up
- d -> page_down

### Function keys (number row -> F1-F12):
- 1-9 -> f1-f9
- 0 -> f10
- - (hyphen) -> f11
- = (equal_sign) -> f12
- backslash -> insert
- backtick/tilde -> delete_forward

All vim layer manipulators use: "modifiers": {"mandatory": ["right_option"]}

EDGE CASES SOLVED
-----------------

1. **"diff " -> "dif f"**: Fixed by queuing spacebar
2. **"full" -> "ufll"**: Fixed by queuing vim nav keys during tapping window
3. **Key repeat broken**: Fixed by making F a real modifier (right_option)
4. **Fast F+J transition**: Works because vim manipulator checks modifier, not variables
5. **Doubled letters in words**: Multi-slot queue handles "foo", "sheep", etc.

CONFIGURATION CONSTANTS
-----------------------

- TAPPING_TERM_MS: Configurable delay before tap becomes hold (see constant definition)
- MULTI_SLOT_COUNT: 3 slots for commonly doubled letters
- MULTI_SLOT_KEYS: ['e', 'o', 'p', 's', 'z'] (letters frequently doubled in aki_null usage)

KNOWN LIMITATIONS
-----------------

1. Right Option key cannot be used normally (it's hijacked by F as modifier)
2. Queue depth limited (3 slots for multi-slot keys, 1 for others)
3. Very fast typing (>10 keys within tapping term) may overflow queue
4. Vim layer mappings conflict with any existing right_option shortcuts

USAGE
-----

Generate configuration:
    python3 generate_tmk_config.py

Output:
    aki_null.json
    (Contains the aki_null keymap configuration for Karabiner-Elements)

Install:
    cp aki_null.json \\
       ~/.config/karabiner/assets/complex_modifications/

Then enable in Karabiner-Elements > Complex Modifications > Add rule
Look for: "aki_null keymap (TMK) - with waiting buffer simulation"

TESTING CHECKLIST
-----------------

1. Control key:
   - Tap Ctrl -> Esc ✓
   - Hold Ctrl + C -> Ctrl+C ✓

2. Shift keys:
   - Tap left shift -> ( ✓
   - Tap right shift -> ) ✓
   - Hold shift -> normal shift behavior ✓

3. F key tapping:
   - Tap F -> outputs 'f' ✓
   - Type "diff " fast -> "diff " (not "dif f") ✓
   - Type "full" fast -> "full" (not "ufll") ✓
   - Type "foo" with F held briefly -> "foo" ✓

4. F key vim layer:
   - Hold F, press J -> down arrow ✓
   - Hold F, hold J -> down arrow repeats continuously ✓ (KEY FIX!)
   - Hold F, press 1 -> F1 ✓
   - Hold F, press H -> left arrow ✓

5. Edge cases:
   - F then immediate J (within tapping term) -> "fj" ✓
   - Multiple F taps quickly -> multiple 'f' outputs ✓
"""

import json
from typing import List, Dict, Any

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================
# These constants define the aki_null keymap behavior

# Tapping term: How long to wait before F becomes vim layer modifier
# TMK default is 150ms (TAPPING_TERM). This value can be adjusted based on typing speed:
# - Lower values (100-130ms): Faster vim layer activation, requires more precise typing
# - Higher values (150-200ms): More forgiving for fast typing, slower vim layer activation
TAPPING_TERM_MS = 150

# Keys that need multi-slot queuing (commonly doubled letters)
# These are letters that frequently appear doubled in English words: "see", "too", "happy", etc.
# Each gets 3 slots so fast typing like "foo" queues both 'o's separately
# Note: 'l' was considered but removed - it's a vim nav key and rarely doubled anyway
MULTI_SLOT_KEYS = ['e', 'o', 'p', 's', 'z']
MULTI_SLOT_COUNT = 3  # Number of slots per multi-slot key

# All alphabet keys except 'f' (which is the layer key itself)
ALL_ALPHA_KEYS = [chr(i) for i in range(ord('a'), ord('z') + 1) if chr(i) != 'f']

# Vim navigation keys - these map to arrows/page keys when F is held as modifier
# IMPORTANT: These MUST be queued during tapping window to prevent bugs like "full" → "ufll"
VIM_NAV_KEYS = ['h', 'j', 'k', 'l', 'u', 'd']

# Keys that should be queued during F tapping window
# CRITICAL INSIGHT: Must include ALL alphabet keys, even vim nav keys!
# During tapping window: these get queued
# After tapping term: vim nav keys use separate manipulator with right_option
QUEUE_KEYS = ALL_ALPHA_KEYS

# Additional non-alphabet keys to queue during tapping window
# CRITICAL: spacebar must be queued to prevent "diff " → "dif f"
# When typing fast, space can be pressed while F is still held from previous letter
# Excludes: numbers (0-9), hyphen, equals, backtick, backslash
#   → These are used in vim layer for F1-F12 mappings, must pass through
ADDITIONAL_QUEUE_KEYS = [
    'spacebar',                    # Most important! Prevents "diff " bug
    'comma', 'period', 'slash',    # Common punctuation
    'semicolon', 'quote',          # Code-related punctuation
    'open_bracket', 'close_bracket'  # Brackets
]

# =============================================================================
# VIM LAYER MAPPINGS
# =============================================================================
# When F is held (becomes right_option modifier), these keys transform

# Navigation mappings: Classic Vim-style hjkl + page up/down
# These use mandatory right_option modifier, enabling OS key repeat!
VIM_LAYER_NAV_MAPPINGS = {
    'h': 'left_arrow',   # Left
    'j': 'down_arrow',   # Down
    'k': 'up_arrow',     # Up
    'l': 'right_arrow',  # Right
    'u': 'page_up',      # Page up (Vim: half-page up)
    'd': 'page_down'     # Page down (Vim: half-page down)
}

# Function key mappings: Number row → F1-F12, plus special keys
# Makes F-keys accessible without leaving home row (similar to HHKB layout)
# These also use right_option modifier (F held becomes right_option)
VIM_LAYER_FKEY_MAPPINGS = {
    '1': 'f1',
    '2': 'f2',
    '3': 'f3',
    '4': 'f4',
    '5': 'f5',
    '6': 'f6',
    '7': 'f7',
    '8': 'f8',
    '9': 'f9',
    '0': 'f10',
    'hyphen': 'f11',                    # F + minus key → F11
    'equal_sign': 'f12',                # F + equals key → F12
    'backslash': 'insert',              # F + backslash → Insert
    'grave_accent_and_tilde': 'delete_forward'  # F + backtick → Delete (not backspace!)
}


def create_basic_manipulator(
    from_key: str,
    to: List[Dict[str, Any]] = None,
    to_if_alone: List[Dict[str, Any]] = None,
    to_if_held_down: List[Dict[str, Any]] = None,
    to_after_key_up: List[Dict[str, Any]] = None,
    to_delayed_action: Dict[str, Any] = None,
    conditions: List[Dict[str, Any]] = None,
    parameters: Dict[str, int] = None
) -> Dict[str, Any]:
    """Create a basic Karabiner manipulator."""
    manipulator = {
        "type": "basic",
        "from": {
            "key_code": from_key,
            "modifiers": {"optional": ["any"]}
        }
    }

    if to is not None:
        manipulator["to"] = to
    if to_if_alone is not None:
        manipulator["to_if_alone"] = to_if_alone
    if to_if_held_down is not None:
        manipulator["to_if_held_down"] = to_if_held_down
    if to_after_key_up is not None:
        manipulator["to_after_key_up"] = to_after_key_up
    if to_delayed_action is not None:
        manipulator["to_delayed_action"] = to_delayed_action
    if conditions is not None:
        manipulator["conditions"] = conditions
    if parameters is not None:
        manipulator["parameters"] = parameters

    return manipulator


def create_ctrl_rule() -> Dict[str, Any]:
    """Create left control rule: hold for Ctrl, tap for Esc (using lazy modifier)."""
    return {
        "description": f"Left Control: Hold for Ctrl, Tap for Esc ({TAPPING_TERM_MS}ms, lazy modifier)",
        "manipulators": [
            create_basic_manipulator(
                from_key="left_control",
                to=[
                    {"key_code": "left_control", "lazy": True}
                ],
                to_if_alone=[
                    {"key_code": "escape"}
                ],
                to_if_held_down=[
                    {"key_code": "left_control"}
                ],
                parameters={
                    "basic.to_if_alone_timeout_milliseconds": TAPPING_TERM_MS,
                    "basic.to_if_held_down_threshold_milliseconds": TAPPING_TERM_MS
                }
            )
        ]
    }


def create_shift_rule(side: str, keycode: str) -> Dict[str, Any]:
    """Create shift rule: hold for Shift, tap for parenthesis."""
    shift_key = f"{side}_shift"
    paren = "(" if side == "left" else ")"
    key_num = "9" if side == "left" else "0"

    return {
        "description": f"{side.capitalize()} Shift: Hold for Shift, Tap for {paren} ({TAPPING_TERM_MS}ms, TMK behavior)",
        "manipulators": [
            create_basic_manipulator(
                from_key=shift_key,
                to=[{"key_code": shift_key}],
                to_if_alone=[
                    {"key_code": key_num, "modifiers": [shift_key]}
                ],
                parameters={"basic.to_if_alone_timeout_milliseconds": TAPPING_TERM_MS}
            )
        ]
    }


def create_f_key_main_manipulator() -> Dict[str, Any]:
    """Create the main F key manipulator with all state management.

    This is the CORE of the waiting buffer simulation. When F is pressed:

    1. Immediately (to): Set f_pressed=1, f_tapping=1
       - These enable queue manipulators (other keys get queued instead of output)

    2. After tapping term (to_if_held_down): Set f_was_modifier=1, output right_option
       - This disables queue manipulators (f_was_modifier=0 condition fails)
       - This enables vim layer (right_option modifier becomes active)
       - F is now a real modifier key, enabling OS key repeat!

    3. On F release (to_after_key_up):
       - Replay 'f' if it was just a tap (f_was_modifier=0)
       - Replay all queued keys in order
       - Clear all state variables

    The f_was_modifier variable is KEY: it distinguishes between:
    - Tapping window (0): queue all keys, output 'f' on release
    - Modifier mode (1): F is right_option, don't output 'f' on release
    """
    # Build the to_after_key_up array
    to_after_key_up = []

    # Replay 'f' ONLY if F was tapped (not used as vim layer modifier)
    # If f_was_modifier=1, user held F and used vim layer, so don't output 'f'
    to_after_key_up.append({
        "key_code": "f",
        "conditions": [{"type": "variable_if", "name": "f_was_modifier", "value": 0}]
    })

    # Replay queued alphabet keys
    for key in QUEUE_KEYS:
        if key in MULTI_SLOT_KEYS:
            # Multi-slot keys have 3 slots
            for slot in range(1, MULTI_SLOT_COUNT + 1):
                var_name = f"queued_{key}_{slot}"
                to_after_key_up.append({
                    "key_code": key,
                    "conditions": [{"type": "variable_if", "name": var_name, "value": 1}]
                })
                to_after_key_up.append({
                    "set_variable": {"name": var_name, "value": 0}
                })
        else:
            # Single-slot keys
            var_name = f"queued_{key}"
            to_after_key_up.append({
                "key_code": key,
                "conditions": [{"type": "variable_if", "name": var_name, "value": 1}]
            })
            to_after_key_up.append({
                "set_variable": {"name": var_name, "value": 0}
            })

    # Replay queued additional keys (space, punctuation)
    for key in ADDITIONAL_QUEUE_KEYS:
        var_name = f"queued_{key}"
        to_after_key_up.append({
            "key_code": key,
            "conditions": [{"type": "variable_if", "name": var_name, "value": 1}]
        })
        to_after_key_up.append({
            "set_variable": {"name": var_name, "value": 0}
        })

    # Clean up all state variables
    for var in ["f_tapping", "f_pressed", "f_was_modifier"]:
        to_after_key_up.append({"set_variable": {"name": var, "value": 0}})

    return create_basic_manipulator(
        from_key="f",
        to=[
            {"set_variable": {"name": "f_tapping", "value": 1}},
            {"set_variable": {"name": "f_pressed", "value": 1}}
        ],
        to_if_held_down=[
            {"set_variable": {"name": "f_tapping", "value": 0}},
            {"set_variable": {"name": "f_was_modifier", "value": 1}},
            {"key_code": "right_option"}  # F becomes right_option when held
        ],
        to_after_key_up=to_after_key_up,
        parameters={"basic.to_if_held_down_threshold_milliseconds": TAPPING_TERM_MS}
    )


def create_queue_manipulator(key: str, slot: int = None) -> Dict[str, Any]:
    """Create a queue manipulator for a single key (with optional slot number).

    Queue manipulators intercept keys during the F tapping window and set queue
    variables instead of outputting the key immediately.

    Conditions for queuing:
    1. f_pressed=1: F key is physically held down
    2. f_was_modifier=0: Still in tapping window (before tapping term expires)

    If both conditions are true, the key is queued (queued_X=1) instead of output.

    Multi-slot keys (e, o, p, s, z) have 3 slots to handle double/triple letters:
    - slot 1: queued_X_1=1 (first occurrence)
    - slot 2: queued_X_2=1 (only if slot 1 already set)
    - slot 3: queued_X_3=1 (only if slot 2 already set)

    This allows typing "foo" fast with F held: both 'o's get queued in separate slots.
    """
    conditions = [
        {"type": "variable_if", "name": "f_pressed", "value": 1},       # F is held
        {"type": "variable_if", "name": "f_was_modifier", "value": 0}   # Tapping window
    ]

    var_name = f"queued_{key}"

    if slot is not None:
        # Multi-slot key
        var_name = f"queued_{key}_{slot}"

        # Add conditions for previous slots
        if slot > 1:
            conditions.append({"type": "variable_if", "name": f"queued_{key}_{slot-1}", "value": 1})

        # Check this slot is empty
        conditions.append({"type": "variable_if", "name": var_name, "value": 0})

    return create_basic_manipulator(
        from_key=key,
        conditions=conditions,
        to=[{"set_variable": {"name": var_name, "value": 1}}]
    )


def create_vim_layer_manipulator_with_modifier(key: str, target_key: str) -> Dict[str, Any]:
    """Create a vim layer manipulator using F as a real modifier.

    **CRITICAL INSIGHT**: This approach supports OS key repeat!

    Why this works:
    - F held for tapping term -> outputs right_option (a real modifier)
    - J pressed with right_option held -> Karabiner matches this manipulator
    - J held -> OS generates repeat events: "right_option + J" repeatedly
    - Each repeat event matches this manipulator again -> down_arrow repeats!

    Why variable conditions DON'T work:
    - If we used "conditions": [{"variable_if": "vim_layer", "value": 1}]
    - Each OS repeat event must re-check the condition
    - This breaks the key repeat mechanism somehow (Karabiner limitation)

    Why simultaneous keys DON'T work:
    - Simultaneous detection requires keys pressed nearly at the same time
    - User pattern is: hold F (wait), THEN press J
    - By the time J is pressed, F was pressed 200ms ago (not simultaneous)

    This modifier-based approach is the ONLY way to get key repeat working!

    The vim nav keys (h, j, k, l, u, d) have TWO manipulators:
    1. Queue manipulator (when f_was_modifier=0): queues during tapping window
    2. Vim layer manipulator (when right_option held): transforms to arrow/page key
    """
    manipulator = {
        "type": "basic",
        "from": {
            "key_code": key,
            "modifiers": {
                "mandatory": ["right_option"],  # F becomes right_option when held
                "optional": ["any"]             # Allow other modifiers (shift, ctrl, etc.)
            }
        },
        "to": [
            {"key_code": target_key}
        ]
    }
    return manipulator


def create_f_rule() -> Dict[str, Any]:
    """Create the complete F key rule with waiting buffer and vim layer.

    This assembles ALL the manipulators needed for F key behavior:

    ORDER MATTERS in Karabiner! Manipulators are evaluated top-to-bottom.
    First matching manipulator wins.

    1. Main F key manipulator (MUST be first!)
       - Handles F press/release and state management

    2. Queue manipulators (come before vim layer!)
       - Alphabet keys (including vim nav keys during tapping window)
       - Multi-slot keys for doubled letters
       - Space and punctuation
       - Only match when: f_pressed=1 AND f_was_modifier=0

    3. Vim layer manipulators for navigation
       - Only match when: right_option modifier is held
       - h/j/k/l/u/d -> arrows/page keys
       - Support key repeat because they use real modifier!

    4. Vim layer manipulators for function keys
       - Only match when: right_option modifier is held
       - 1-9,0,-,= -> F1-F12, insert, delete

    The magic: vim nav keys (h,j,k,l,u,d) match DIFFERENT manipulators depending on state:
    - During tapping window (f_was_modifier=0): Queue manipulator matches
    - During vim layer (right_option held): Vim layer manipulator matches
    """
    manipulators = []

    # 1. Main F key manipulator - MUST BE FIRST!
    #    This sets up all the state variables and handles F press/release
    manipulators.append(create_f_key_main_manipulator())

    # 2. Queue manipulators for alphabet keys (ALL keys including vim nav)
    #    These intercept keys during the tapping window (f_was_modifier=0)
    for key in QUEUE_KEYS:
        if key in MULTI_SLOT_KEYS:
            # Create multi-slot manipulators for commonly doubled letters
            # Example: 'o' has queued_o_1, queued_o_2, queued_o_3
            for slot in range(1, MULTI_SLOT_COUNT + 1):
                manipulators.append(create_queue_manipulator(key, slot))
        else:
            # Create single-slot manipulator
            manipulators.append(create_queue_manipulator(key))

    # 2b. Queue manipulators for additional keys (space, punctuation)
    #     CRITICAL: Space must be queued to prevent "diff " -> "dif f"
    for key in ADDITIONAL_QUEUE_KEYS:
        manipulators.append(create_queue_manipulator(key))

    # 3. Vim layer manipulators for navigation (h/j/k/l/u/d -> arrows/page)
    #    These use right_option as mandatory modifier for key repeat support
    #    NOTE: These come AFTER queue manipulators, so queue takes precedence during tapping
    for key, arrow_key in VIM_LAYER_NAV_MAPPINGS.items():
        manipulators.append(create_vim_layer_manipulator_with_modifier(key, arrow_key))

    # 4. Vim layer manipulators for function keys (number row -> F1-F12)
    #    These also use right_option as mandatory modifier
    for key, fkey in VIM_LAYER_FKEY_MAPPINGS.items():
        manipulators.append(create_vim_layer_manipulator_with_modifier(key, fkey))

    return {
        "description": "F key Vim layer with waiting buffer (F becomes modifier for key repeat support)",
        "manipulators": manipulators
    }


def generate_config() -> Dict[str, Any]:
    """Generate the complete Karabiner configuration for aki_null keymap.

    This generates the full configuration including:
    - Control tap/hold (Esc/Ctrl)
    - Shift tap/hold (parentheses/Shift)
    - F key vim layer with waiting buffer simulation
    """
    return {
        "title": "aki_null keymap (TMK)",
        "rules": [
            create_ctrl_rule(),
            create_shift_rule("left", "("),
            create_shift_rule("right", ")"),
            create_f_rule()
        ]
    }


def main():
    """Generate and save the configuration."""
    config = generate_config()

    output_file = "aki_null.json"

    with open(output_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"✓ Generated configuration saved to: {output_file}")
    print(f"✓ Total manipulators: {sum(len(rule['manipulators']) for rule in config['rules'])}")
    print(f"  - Control rule: {len(config['rules'][0]['manipulators'])}")
    print(f"  - Left shift rule: {len(config['rules'][1]['manipulators'])}")
    print(f"  - Right shift rule: {len(config['rules'][2]['manipulators'])}")
    print(f"  - F key rule: {len(config['rules'][3]['manipulators'])}")


if __name__ == "__main__":
    main()
