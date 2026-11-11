//! Terminal text operations. Bytes use Python's UTF-8 surrogate-pass representation.
use alloc::{string::String, vec, vec::Vec};

fn cp(text: &[u8], at: usize) -> (u32, usize) {
    let b = text[at];
    let len = match b {
        0..=0x7f => 1,
        0xc0..=0xdf => 2,
        0xe0..=0xef => 3,
        0xf0..=0xf7 => 4,
        _ => 1,
    }
    .min(text.len() - at);
    let mut value = u32::from(
        b & match len {
            1 => 0xff,
            2 => 0x1f,
            3 => 0x0f,
            _ => 7,
        },
    );
    for &b in &text[at + 1..at + len] {
        value = (value << 6) | u32::from(b & 0x3f);
    }
    (value, len)
}
fn csi_end(text: &[u8], start: usize) -> Option<usize> {
    if text.get(start..start + 2) != Some(b"\x1b[") {
        return None;
    }
    let mut at = start + 2;
    while text.get(at).is_some_and(|b| (0x30..=0x3f).contains(b)) {
        at += 1;
    }
    while text.get(at).is_some_and(|b| (0x20..=0x2f).contains(b)) {
        at += 1;
    }
    if text.get(at).is_some_and(|b| (0x40..=0x7e).contains(b)) {
        Some(at + 1)
    } else {
        None
    }
}
/// Strip complete ECMA-48 CSI sequences. Incomplete and non-CSI escapes survive.
pub fn strip_ansi(text: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(text.len());
    let mut i = 0;
    while i < text.len() {
        if let Some(end) = csi_end(text, i) {
            i = end;
        } else {
            out.push(text[i]);
            i += 1;
        }
    }
    out
}
/// Click measures visible Unicode codepoints, not terminal display cells.
pub fn text_width(text: &[u8]) -> usize {
    let mut count = 0;
    let mut i = 0;
    while i < text.len() {
        if let Some(end) = csi_end(text, i) {
            i = end;
        } else {
            i += cp(text, i).1;
            count += 1;
        }
    }
    count
}
fn cut_visible(text: &[u8], n: usize) -> usize {
    if n == 0 {
        return 0;
    }
    let mut count = 0;
    let mut i = 0;
    let mut cut = 0;
    while i < text.len() {
        if let Some(end) = csi_end(text, i) {
            i = end;
            continue;
        }
        i += cp(text, i).1;
        cut = i;
        count += 1;
        if count >= n {
            break;
        }
    }
    cut
}
/// Return a visible prefix without slicing a CSI escape or Unicode codepoint.
pub fn truncate_visible(text: &[u8], n: usize) -> Vec<u8> {
    text[..cut_visible(text, n)].to_vec()
}
fn whitespace(code: u32) -> bool {
    matches!(code, 0x1c..=0x1f) || char::from_u32(code).is_some_and(char::is_whitespace)
}
fn blank(text: &[u8]) -> bool {
    let mut i = 0;
    while i < text.len() {
        let (c, n) = cp(text, i);
        if !whitespace(c) {
            return false;
        }
        i += n;
    }
    true
}
fn trim_start(text: &[u8]) -> &[u8] {
    let mut i = 0;
    while i < text.len() {
        let (c, n) = cp(text, i);
        if !whitespace(c) {
            break;
        }
        i += n;
    }
    &text[i..]
}
fn trim(text: &[u8]) -> &[u8] {
    let text = trim_start(text);
    let mut i = 0;
    let mut last = 0;
    while i < text.len() {
        let (c, n) = cp(text, i);
        i += n;
        if !whitespace(c) {
            last = i;
        }
    }
    &text[..last]
}
fn expand_tabs(text: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(text.len());
    let mut col = 0;
    let mut i = 0;
    while i < text.len() {
        let (c, n) = cp(text, i);
        if c == 9 {
            let count = 8 - col % 8;
            out.resize(out.len() + count, b' ');
            col += count;
        } else {
            out.extend_from_slice(&text[i..i + n]);
            if c == 10 || c == 13 {
                col = 0;
            } else {
                col += 1;
            }
        }
        i += n;
    }
    out
}
fn split_lines(text: &[u8]) -> Vec<&[u8]> {
    let mut lines = Vec::new();
    let mut start = 0;
    let mut i = 0;
    while i < text.len() {
        let (c, n) = cp(text, i);
        if matches!(c,10..=13|0x1c..=0x1e|0x85|0x2028|0x2029) {
            lines.push(&text[start..i]);
            i += n;
            if c == 13 && text.get(i) == Some(&10) {
                i += 1;
            }
            start = i;
        } else {
            i += n;
        }
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}
fn letter(c: u32) -> bool {
    char::from_u32(c).is_some_and(char::is_alphabetic)
}
fn word(c: u32) -> bool {
    c == b'_' as u32 || char::from_u32(c).is_some_and(char::is_alphanumeric)
}
fn chunks(text: &[u8]) -> Vec<Vec<u8>> {
    let mut out = Vec::new();
    let mut start = 0;
    let mut i = 0;
    while i < text.len() {
        let space = matches!(text[i], b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c);
        if space {
            let mut end = i + 1;
            while end < text.len()
                && matches!(text[end], b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
            {
                end += 1;
            }
            if start < i {
                out.push(text[start..i].to_vec());
            }
            out.push(text[i..end].to_vec());
            i = end;
            start = end;
            continue;
        }
        if text[i] == b'-' {
            let mut end = i + 1;
            while text.get(end) == Some(&b'-') {
                end += 1;
            }
            let preceding = text[..i]
                .iter()
                .rposition(|b| b & 0xc0 != 0x80)
                .map(|p| cp(text, p).0);
            let next = if end < text.len() {
                Some(cp(text, end).0)
            } else {
                None
            };
            if end - i >= 2
                && preceding
                    .is_some_and(|c| word(c) || matches!(c, 33 | 34 | 39 | 38 | 46 | 44 | 63))
                && next.is_some_and(word)
            {
                if start < i {
                    out.push(text[start..i].to_vec());
                }
                out.push(text[i..end].to_vec());
                i = end;
                start = end;
                continue;
            }
            if end - i == 1 {
                let before: Vec<_> = text[..i]
                    .iter()
                    .enumerate()
                    .filter(|(_, b)| **b & 0xc0 != 0x80)
                    .map(|(p, _)| cp(text, p).0)
                    .rev()
                    .take(3)
                    .collect();
                let mut nexts = Vec::new();
                let mut p = end;
                while p < text.len() && nexts.len() < 3 {
                    let (c, n) = cp(text, p);
                    nexts.push(c);
                    p += n;
                }
                let left = before.len() >= 2 && letter(before[0]) && letter(before[1])
                    || before.len() >= 3
                        && letter(before[0])
                        && before[1] == 45
                        && letter(before[2]);
                let right = nexts.len() >= 2
                    && letter(nexts[0])
                    && (letter(nexts[1]) || nexts.len() >= 3 && nexts[1] == 45 && letter(nexts[2]));
                if left && right {
                    out.push(text[start..end].to_vec());
                    i = end;
                    start = end;
                    continue;
                }
            }
        }
        i += cp(text, i).1;
    }
    if start < text.len() {
        out.push(text[start..].to_vec());
    }
    out
}
fn fill(text: &[u8], width: usize, initial: &[u8], subsequent: &[u8]) -> Vec<u8> {
    let mut pieces = chunks(text);
    let mut index = 0;
    let mut lines: Vec<Vec<u8>> = Vec::new();
    while index < pieces.len() {
        let indent = if lines.is_empty() {
            initial
        } else {
            subsequent
        };
        let available = width as isize - text_width(indent) as isize;
        if !lines.is_empty() && blank(&pieces[index]) {
            index += 1;
            if index == pieces.len() {
                break;
            }
        }
        let mut line: Vec<Vec<u8>> = Vec::new();
        let mut used = 0isize;
        while index < pieces.len() {
            let len = text_width(&pieces[index]) as isize;
            if used + len > available {
                break;
            }
            used += len;
            line.push(core::mem::take(&mut pieces[index]));
            index += 1;
        }
        if index < pieces.len() && text_width(&pieces[index]) as isize > available {
            let cut = cut_visible(&pieces[index], (available - used).max(1) as usize);
            if cut == 0 {
                line.push(core::mem::take(&mut pieces[index]));
                index += 1;
            } else {
                let tail = pieces[index].split_off(cut);
                line.push(core::mem::replace(&mut pieces[index], tail));
                if pieces[index].is_empty() {
                    index += 1;
                }
            }
        }
        if line.last().is_some_and(|s| blank(s)) {
            line.pop();
        }
        if !line.is_empty() {
            let mut rendered = indent.to_vec();
            for part in line {
                rendered.extend(part);
            }
            lines.push(rendered);
        }
    }
    let mut out = Vec::new();
    for (i, line) in lines.iter().enumerate() {
        if i > 0 {
            out.push(b'\n');
        }
        out.extend(line);
    }
    out
}
/// Wrap Click help text, including explicit raw paragraphs and ANSI-aware widths.
pub fn wrap_text(
    text: &[u8],
    width: usize,
    initial: &[u8],
    subsequent: &[u8],
    preserve: bool,
) -> Result<Vec<u8>, String> {
    if width == 0 {
        return Err("invalid width 0 (must be > 0)".into());
    }
    let text = expand_tabs(text);
    if !preserve {
        return Ok(fill(&text, width, initial, subsequent));
    }
    let mut paragraphs: Vec<(usize, Vec<&[u8]>)> = Vec::new();
    let mut current: Vec<&[u8]> = Vec::new();
    let mut indent = 0;
    for line in split_lines(&text) {
        if line.is_empty() {
            if !current.is_empty() {
                paragraphs.push((indent, core::mem::take(&mut current)));
            }
        } else {
            let line = if current.is_empty() {
                let trimmed = trim_start(line);
                indent = text_width(line) - text_width(trimmed);
                trimmed
            } else {
                line
            };
            current.push(line);
        }
    }
    if !current.is_empty() {
        paragraphs.push((indent, current));
    }
    let mut out = Vec::new();
    for (number, (indent, lines)) in paragraphs.into_iter().enumerate() {
        if number > 0 {
            out.extend_from_slice(b"\n\n");
        }
        let mut first = initial.to_vec();
        first.extend(vec![b' '; indent]);
        let mut next = subsequent.to_vec();
        next.extend(vec![b' '; indent]);
        let raw = lines.first().is_some_and(|s| trim(s) == b"\x08");
        if raw {
            for (i, line) in lines.iter().skip(1).enumerate() {
                if i > 0 {
                    out.push(b'\n');
                }
                out.extend(if i == 0 { &first } else { &next });
                out.extend_from_slice(line);
            }
        } else {
            let mut joined = Vec::new();
            for (i, line) in lines.iter().enumerate() {
                if i > 0 {
                    joined.push(b' ');
                }
                joined.extend_from_slice(line);
            }
            out.extend(fill(&joined, width, &first, &next));
        }
    }
    Ok(out)
}
/// Stable prefix-length ordering used by option help records.
pub fn join_options(options: &[Vec<u8>]) -> (Vec<u8>, bool) {
    let mut ordered: Vec<_> = options.iter().collect();
    let mut slash = false;
    ordered.sort_by_key(|s| {
        if s.first() == Some(&b'/') && s.get(1) != Some(&b'/') {
            slash = true;
        }
        if s.is_empty() {
            return 0;
        }
        let (first, n) = cp(s, 0);
        if char::from_u32(first).is_some_and(char::is_alphanumeric) {
            return 0;
        }
        if n == s.len() {
            0
        } else if cp(s, n).0 == first {
            2
        } else {
            1
        }
    });
    // sort_by_key may not call the key closure for an empty or one-item slice.
    slash |= options
        .iter()
        .any(|s| s.first() == Some(&b'/') && s.get(1) != Some(&b'/'));
    let mut out = Vec::new();
    for (i, s) in ordered.iter().enumerate() {
        if i > 0 {
            out.extend_from_slice(b", ");
        }
        out.extend_from_slice(s);
    }
    (out, slash)
}
