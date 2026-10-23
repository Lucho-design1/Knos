# Task: parse a duration (a Knos coding task, posted by a team for a coding agent)

Write `parse_duration(text)` in `duration.py`: it turns a human duration into whole seconds.

- Units: `d` (days), `h` (hours), `m` (minutes), `s` (seconds); e.g. `"1h30m"` is 5400, `"45s"` is 45, `"2d"` is 172800.
- Parts may be separated by spaces (`"1h 5m 10s"`), each unit appears at most once, larger units first.
- Upper case units are accepted (`"2H"`), surrounding spaces are ignored.
- A bare number with no unit, an empty string, an unknown unit, a repeated unit, units out of order, a sign or a
  decimal point raise `ValueError`.

You may change `duration.py` and add tests under `tests/`. Nothing else. A sealed set of acceptance tests that you never
see decides whether the work is accepted (the Knos referee); the payment program pays only on that verdict.
