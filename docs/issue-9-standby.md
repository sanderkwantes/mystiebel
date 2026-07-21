# Issue #9 — "Missing Standby function"

## The issue

> For controlling my Stiebel using the SG_Ready implementation, it would be
> helpfull to put the heatpump into standby state like the extended function
> "Standby" in the my Stiebel app.

`parameters.json` (the bundled register/translation dump) had no register
anywhere with "standby" in its id, translation, or choice list text —
confirmed by grep across all three before starting this investigation.
So the register backing this feature was genuinely undocumented, not just
unexposed.

## Finding: it isn't a new register, it's an existing one

Standby is not a distinct control. Toggling it in the app writes the same
register already wired up as `switch.frost_protection_requested`
(register 2384, `ODB_Frostschu_Anf` — German for "frost protection
request").

Proved with a live before/after capture against the real integration
(`terryrankine/mystiebel`, WWK-I 300, installation id 248758):

1. Temporarily widened the coordinator's `active_fields` to also poll/subscribe
   registers 2340–2820 (an unmapped band around the known extended-function
   registers: Boost 2380–2388, Hot Water Plus 2487, Frost Protection 2384,
   End of Vacation 2481, Operating Mode 2758).
2. Captured a baseline of every register value in that range via
   `custom_components.mystiebel` debug logging.
3. Toggled Standby **on** in the myStiebel app (Extended functions → Standby).
4. Diffed the register dump. Two things moved:
   - **2758** (`WWK_OperationMode`, already exposed as `sensor.operating_mode`,
     read-only) went `7` (`comfortMode`) → `4` (`frostProtectionHolidayMode`).
   - **2384** itself flipped `0` → `1` — this is the write-side trigger, and
     it was *already* a wired-up entity (`switch.frost_protection_requested`,
     part of `ESSENTIAL_CONTROLS`).
5. Confirmed causality both ways, from the HA side rather than the app side:
   flipped `switch.frost_protection_requested` **off** via a plain HA service
   call (not the app) — `sensor.operating_mode` dropped to `Comfort mode`
   within ~4 seconds. Flipped it back **on** — back to
   `Frost protection holiday mode` within ~4 seconds. Restored to the
   original (Standby on) state afterwards.

So the feature already existed in every fork/release using this codebase.
It just isn't discoverable, because the entity is named after the German
internal register name instead of what the app calls it.

## Fix

Renamed the English display string only (`parameters.json` → `texts` →
`ODB_Frostschu_Anf` → `en`):

```diff
-      "en": "Frost protection requested",
+      "en": "Standby (Frost Protection)",
```

Entity ID is unaffected (`switch.frost_protection_requested` — HA generates
that once from the register name, not the display text, so no migration,
no re-added entity, existing automations referencing it keep working).

`const.py`'s `ESSENTIAL_CONTROLS` comment updated to cross-reference #9.

## Translations

This entity doesn't use HA's own `translations/*.json` mechanism — that
folder only backs the entities that set `translation_key`
(the combined/runtime/calculated/alarm sensors in `sensor.py`).
`MyStiebelSwitch` takes its name straight from `parameters.json`'s own
`texts` blob per register, so the `en` edit above is the entire fix.

Other locales (de/fr/es/it/nl/sl/pl/cs/hu/sk) still read as "frost
protection requested" in their own language — still technically accurate,
just not discoverable as "Standby" by non-English speakers. Not fixed here;
would need a native speaker per language to know what Stiebel's own app
calls it locally. Left as a follow-up.

## Not changed

No new parameter, no new entity, no new Python. `switch.py`'s existing
generic logic (any `read_write` + `choicelist_id == "State_on_off"` param)
already covers this register — that's why nothing needed touching there.
