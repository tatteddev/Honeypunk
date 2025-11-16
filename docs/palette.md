# Honeydrunk Palette Mapping

| Color Name     | Hex      | Theme Usage |
| -------------- | -------- | ----------- |
| Deep Space     | #0A0E12  | Primary app background, document canvas, editor gutter. |
| Gunmetal       | #111827  | Panels, tool windows, collapsible chrome, definition popups. |
| Electric Blue  | #00D1FF  | Primary accent for selections, active tabs, indicators, file/tab names, output window text. |
| Electric Blue 80% | #00D1FFCC | Hover state fills, pressed buttons. |
| Electric Blue 20% | #00D1FF33 | Selection overlays, line highlights. |
| Aurum Gold     | #F5B700  | Numbers, warnings with positive emphasis, markup attributes, extension ratings. |
| Cyber Orange   | #FF8C00  | C# control-flow keywords (if/try/await/throw), warnings, syntax diagnostics, attention glyphs. |
| Matrix Green   | #00FF41  | C++ literals/punctuation/parameters, success callouts. |
| Signal Green   | #22C55E  | Diff/track-changes adds, success overlays. |
| Neon Yellow    | #FFFF00  | Functions (C# methods, extension methods; C++ free/member/static/template functions), snippet dependent fields. |
| Neon Pink      | #FF2A6D  | Strings, selectors, glyphs requiring high-energy contrast. |
| Chrome Teal    | #14B8A6  | Types, interface names, regex grouping. |
| Violet Flux    | #7B61FF  | Preprocessor, namespace cues, neutral anchors. |
| Synth Magenta  | #D946EF  | Variables (C# locals & fields, C++ globals & locals), static classes, base keywords, errors, breakpoint emphasis. |
| Off-White      | #E5E7EB  | High-contrast text for CTA buttons, toggles. |
| Slate Light    | #94A3B8  | Comments, XML doc comments, default text for panels, console windows, metadata. |

Design notes:
- **Contrast pairs**: Deep Space + Off-White for maximum readability; Gunmetal + Slate Light for low eye strain; Electric Blue overlays rest atop Gunmetal for active chrome.
- **Semantic triads**: Synth Magenta (error), Cyber Orange (warning), Signal Green (success) keep diagnostic cues consistent across UI and editor.
- **Code token wheel**: Variables (Synth Magenta), Functions (Neon Yellow), Control-flow keywords (Cyber Orange), Base keywords (Synth Magenta), Types (Chrome Teal), Parameters (Matrix Green), Strings (Neon Pink), Comments (Slate Light), Literals (Aurum Gold) — tuned for rapid visual parsing.
- **Accessibility**: Slate Light meets contrast over Deep Space/Gunmetal, while Electric Blue retains 4.5:1 when used as foreground on Deep Space.
