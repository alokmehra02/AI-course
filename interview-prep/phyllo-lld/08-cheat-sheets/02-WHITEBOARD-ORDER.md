# Whiteboard Order (What to Draw When)

Follow this order every time so you don’t thrash.

```
1. Title + 3–4 requirements bullets
2. Actors (stick figures / labels)
3. Entity boxes (no fields yet)
4. Module boxes: API | Connect | Sync Workers | Normalizer | DB | Queue | Webhook
5. Arrows for happy-path sequence (numbered 1..N)
6. Fill fields on 3–4 core entities
7. API list on the side
8. State machine for Account (small)
9. Failure notes (token expiry, 429, webhook retry)
10. Tradeoff box (2 bullets)
```

---

## Spacing tip

Left: entities + state machine  
Center: sequence  
Right: APIs + schema tables  

---

## If virtual (Google Doc / Excalidraw)

Use headings:
`## Requirements` `## Entities` `## APIs` `## Sequence` `## Schema` `## Failures`
