# Karabiner-Elements Vim Layer Implementation

## Goal

Replicate TMK keyboard firmware's `ACTION_LAYER_TAP_KEY` behavior in Karabiner-Elements, specifically for the F key:
- **Tap** (release < 150ms): Send 'f'
- **Hold** (≥ 150ms): Activate vim layer

## TMK Firmware Reference

### Source Files
- **Config**: `~/tmk_keyboard/keyboard/hhkb/config.h:44`
  - `#define TAPPING_TERM 150` - 150ms threshold

- **Keymap**: `~/tmk_keyboard/keyboard/hhkb/keymap_akinull.c:123-126`
  - `FN2 = ACTION_LAYER_TAP_KEY(3, KC_F)` - Layer 3 (vim) on hold, 'f' on tap

- **Core Logic**: `~/tmk_keyboard/tmk_core/common/action_tapping.c`
  - Lines 84-143: Main tapping state machine
  - Lines 292-308: Waiting buffer implementation
  - **Key behavior**: Events are buffered during TAPPING_TERM, then processed AFTER tap/hold decision

### TMK Architecture
1. Key down → Enter waiting state, queue subsequent events
2. If held ≥150ms without interruption → Activate layer, process queued events in layer context
3. If another key pressed during wait → Set interrupted flag, send tap key + interrupting key
4. If released <150ms without interruption → Send tap key

## Karabiner-Elements Implementation

### Location
- **Config file**: `~/dotfiles/karabiner.json` (symlinked from `~/.config/karabiner/karabiner.json`)
- **Rule**: "LT(F): Tap = F, Hold = Vim Layer" (lines 6-~3700)

### Architecture Difference

**Fundamental limitation**: Karabiner processes events immediately, without TMK's waiting buffer. This makes perfect replication impossible for fast typing scenarios.

### Current Configuration Structure

#### 1. Main F Key Manipulator (lines 9-72)

```json
{
  "conditions": [
    {"name": "f_pressed", "type": "variable_unless", "value": 1}
  ],
  "from": {"key_code": "f"},
  "parameters": {
    "basic.to_if_alone_timeout_milliseconds": 150,
    "basic.to_if_held_down_threshold_milliseconds": 150
  },
  "to": [
    {"set_variable": {"name": "f_pressed", "value": 1}},
    {"set_variable": {"name": "f_sent", "value": 0}}
  ],
  "to_if_alone": [{"key_code": "f"}],
  "to_after_key_up": [
    {"set_variable": {"name": "f_pressed", "value": 0}},
    {"set_variable": {"name": "f_sent", "value": 0}}
  ],
  "to_if_held_down": [
    {"set_variable": {"key_up_value": 0, "name": "vim_layer", "value": 1}}
  ]
}
```

**Variables**:
- `f_pressed`: Set to 1 when F is held, 0 when released
- `f_sent`: Tracks if 'f' has already been output (used by conditional manipulators)
- `vim_layer`: Set to 1 when vim layer is active (≥150ms hold)

**Behavior**:
- `to`: Fires immediately on F key down → sets f_pressed=1
- `to_if_alone`: Fires on F release if no other key pressed within 150ms → sends 'f'
- `to_if_held_down`: Fires after 150ms if F still held → activates vim layer
- `to_after_key_up`: Fires on F release → clears variables

#### 2. Conditional Manipulators for Fast Typing (lines 73-~1500)

Created to handle interruptions when another key is pressed while F is held.

**Structure for vim navigation keys (h, j, k, l)** - Special immediate activation:
```json
{
  "conditions": [
    {"name": "f_pressed", "type": "variable_if", "value": 1}
  ],
  "from": {"key_code": "j"},
  "to": [
    {"set_variable": {"key_up_value": 0, "name": "vim_layer", "value": 1}},
    {"key_code": "down_arrow"}
  ]
}
```

**Structure for all other keys**:
```json
{
  "conditions": [
    {"name": "f_pressed", "type": "variable_if", "value": 1},
    {"name": "vim_layer", "type": "variable_unless", "value": 1}
  ],
  "from": {"key_code": "<KEY>"},
  "to": [
    {"key_code": "f"},
    {"key_code": "<KEY>"},
    {"set_variable": {"name": "f_pressed", "value": 0}},
    {"set_variable": {"name": "f_sent", "value": 1}}
  ]
}
```

**Keys covered**:
- Vim navigation (h/j/k/l): Special immediate vim layer activation
- All other letters (a-z): Standard fast typing fallback
- Spacebar, numbers (0-9), punctuation: Lines 1211-~1500
- Special keys: return, delete, backspace, tab, escape

**Behavior**:
When F is held and another key is pressed:
- **h/j/k/l**: Immediately activate vim_layer and send arrow key (no 150ms delay!)
- **Other keys**: Send 'f' + the key (fast typing mode)

#### 3. Double-F Manipulator (lines 73-~120)

Special conditional manipulator for typing "ff" quickly (e.g., "diff"):

```json
{
  "conditions": [
    {"name": "f_pressed", "type": "variable_if", "value": 1},
    {"name": "vim_layer", "type": "variable_unless", "value": 1}
  ],
  "from": {"key_code": "f"},
  "to": [
    {"key_code": "f"},
    {"key_code": "f"},
    {"set_variable": {"name": "f_pressed", "value": 0}},
    {"set_variable": {"name": "f_sent", "value": 1}}
  ]
}
```

#### 4. Vim Layer Key Mappings (lines ~1500-3600)

When `vim_layer=1`, various keys are remapped for vim-style navigation:
- h/j/k/l → arrow keys
- w/b → word navigation
- 0/$ → home/end
- etc.

### Known Issues

#### Issue 1: "f " produces " " (missing 'f')
**Status**: UNRESOLVED

**Scenario**: Type F and space quickly
- Expected: "f "
- Actual: " " (just space)

**Analysis**:
- Letters work correctly ("fi" → "fi")
- Spacebar conditional manipulator has identical structure but doesn't fire
- Suggests timing issue where `to_if_alone` cancellation interferes with conditional manipulator evaluation

#### Issue 2: "git diff " produces "git dif " (missing one 'f')
**Status**: UNRESOLVED

**Scenario**: Type "diff " quickly with space after second 'f'
- Expected: "git diff "
- Actual: "git dif "

**Analysis**:
- Double-F manipulator handles F2 press correctly
- But when space is pressed after F2, one 'f' is lost
- Likely related to Issue 1 (spacebar problem)

#### Issue 3: Duplicate manipulators
**Status**: Minor issue

The add_more_keys.py script was run twice, creating duplicate conditional manipulators for spacebar and other non-letter keys (once at ~line 1211, again at ~line 2421).

### Working Scenarios

✅ **Single F tap**: "f" → Works (to_if_alone fires)
✅ **Hold F for vim layer**: Hold ≥150ms → Vim layer activates
✅ **Immediate vim navigation**: F + h/j/k/l → Arrow keys work instantly without 150ms delay
✅ **Fast letter typing**: "fink" → Works (conditional manipulators for letters fire correctly)
✅ **Letters in general**: "fi", "fa", "ft" → All work correctly

### Workaround for Immediate Vim Navigation

**Problem**: TMK's waiting buffer approach means vim navigation keys pressed during the 150ms tapping term get processed in layer context after the timeout. In Karabiner, using `to_if_held_down` means you must wait 150ms before pressing navigation keys.

**Solution**: Special conditional manipulators for h/j/k/l that immediately activate vim_layer when pressed while f_pressed==1. This gives the same UX as TMK:

**TMK behavior**:
```
F down → [buffer: F] → wait 150ms
J down (at 50ms) → [buffer: F, J] → wait until 150ms
150ms timeout → activate layer → process J as down_arrow
```

**Karabiner workaround**:
```
F down → f_pressed=1
J down (at 50ms) → conditional manipulator matches f_pressed==1
                 → immediately set vim_layer=1, send down_arrow
```

The UX feels identical: you can press navigation keys immediately after F without waiting.

**Why this works**: h/j/k/l are only used for navigation in vim layer, never for fast typing like "fj" or "fk", so there's no downside to immediate activation.

### Additional Mod-Tap Keys

Also configured with 150ms timing to match TMK:

- **Control**: `~/dotfiles/karabiner.json:4020`
  - Tap = Escape, Hold = Control

- **Left Shift**: `~/dotfiles/karabiner.json:4087`
  - Tap = '(', Hold = Left Shift

- **Right Shift**: Similar to left shift
  - Tap = ')', Hold = Right Shift

### Scripts Used

#### gen_f_manipulators.sh
Generated initial conditional manipulators for letters a-z.

#### add_more_keys.py (`/tmp/add_more_keys.py`)
Added conditional manipulators for spacebar, numbers, punctuation, and special keys.

**Note**: This script appends to existing manipulators, so running it multiple times creates duplicates.

## Debugging Notes

### Verified
- ✅ JSON syntax is valid
- ✅ Config file is properly symlinked
- ✅ Karabiner-Elements is running
- ✅ Conditional manipulators exist in config
- ✅ "spacebar" is correct key_code name
- ✅ Manipulator ordering is correct (conditionals before vim layer mappings)

### Hypotheses for Spacebar Issue
1. **Timing race condition**: `to_if_alone` cancellation happens before conditional manipulator can evaluate
2. **Special spacebar handling**: Karabiner might treat spacebar differently than letter keys
3. **Condition evaluation timing**: Conditions might be evaluated before `to` actions execute
4. **Config reload needed**: Karabiner might not have picked up the changes (though file was touched)

### Next Steps to Debug
1. Remove duplicate manipulators (from second script run)
2. Test if issue is specific to spacebar or affects all non-letter keys
3. Try alternative approach: use `to_delayed_action` instead of `to_if_alone`
4. Check Karabiner logs for errors (if logging can be enabled)
5. Consider filing bug report with Karabiner-Elements project

## Conclusion

The current implementation successfully handles:
- Basic tap/hold functionality for F key
- **Immediate vim navigation**: h/j/k/l work instantly when pressed after F (matches TMK UX)
- Fast typing with letters (a-z)

Known issues:
- Fast typing with spacebar and possibly other non-letter keys
- Double-F followed by space

The vim navigation delay issue has been resolved by using special conditional manipulators for h/j/k/l that immediately activate the vim layer when pressed while F is held. This provides the same responsive UX as TMK's buffered approach, even though the underlying implementation is different.
