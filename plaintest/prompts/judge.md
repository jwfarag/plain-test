# judge

A Check says what should be tested. A second reader, who never saw the Check, described what
a test actually verifies. Decide whether the test is faithful to the Check: same situation,
same action, and an assertion that would fail whenever the Check's "then" doesn't hold.

A test that checks something stronger is faithful. A test that checks something weaker,
different, or only part of it is not.

## The Check

$check

## What the test verifies

$description

## Reply

Reply with JSON only:

```json
{"faithful": true, "reason": "one sentence"}
```
