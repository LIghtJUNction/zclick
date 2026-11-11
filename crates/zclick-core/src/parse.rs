use alloc::{
    borrow::Cow,
    collections::BTreeMap,
    format,
    string::{String, ToString},
    vec,
    vec::Vec,
};
use zclap::{Arg, Command, Event};

/// An invocation-local parameter declaration. Option spellings retain surrogate-pass bytes.
#[derive(Clone, Debug)]
pub struct Spec {
    pub id: i64,
    pub options: Vec<Vec<u8>>,
    pub nargs: i64,
    pub is_flag: bool,
    pub optional_value: bool,
}

/// A syntax error plus enough data for Python exception subclass construction.
#[derive(Clone, Debug)]
pub struct ParseError {
    pub kind: &'static str,
    pub option: Vec<u8>,
    pub id: Option<i64>,
    pub nargs: i64,
    pub message: String,
}

/// Raw occurrences, remaining arguments, and command-line encounter order.
/// Values borrow input storage, including attached values; only reconstructed
/// unknown short clusters require an owned byte string.
#[derive(Debug, Default)]
pub struct ParseResult<'a> {
    pub values: BTreeMap<i64, Vec<Vec<Cow<'a, [u8]>>>>,
    pub leftovers: Vec<Cow<'a, [u8]>>,
    pub order: Vec<i64>,
    pub error: Option<ParseError>,
}

fn codepoint_len(first: u8) -> usize {
    match first {
        0x00..=0x7f => 1,
        0xc0..=0xdf => 2,
        0xe0..=0xef => 3,
        0xf0..=0xf7 => 4,
        _ => 1,
    }
}

fn split_prefix(s: &[u8]) -> (usize, bool) {
    if s.is_empty() {
        return (0, false);
    }
    let first = codepoint_len(s[0]).min(s.len());
    let second = if first < s.len() {
        codepoint_len(s[first]).min(s.len() - first)
    } else {
        0
    };
    let repeated = second != 0 && s[..first] == s[first..first + second];
    (if repeated { first + second } else { first }, repeated)
}

fn is_short(s: &[u8]) -> bool {
    let (prefix, repeated) = split_prefix(s);
    !repeated && prefix < s.len() && prefix + codepoint_len(s[prefix]) == s.len()
}

// zclap deliberately restricts long spellings to portable identifiers. Hex
// framing makes its recognizer usable for every Click prefix without changing
// or losing the original Python spelling. The leading kind separates the
// long and short option namespaces, which Click resolves differently.
fn encode_spelling(s: &[u8], short: bool) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(s.len() * 2 + 1);
    out.push(if short { 's' } else { 'l' });
    for &b in s {
        out.push(HEX[(b >> 4) as usize] as char);
        out.push(HEX[(b & 15) as usize] as char);
    }
    out
}

struct Kernel<'a> {
    commands: Vec<Command<'a>>,
    targets: Vec<usize>,
}
impl Kernel<'_> {
    fn find(&self, spelling: &[u8], short: bool) -> Option<usize> {
        let name = encode_spelling(spelling, short);
        let token = format!("--{name}");
        let argv = [token.as_str()];
        // Chunks keep the kernel's inline presence state bounded while allowing
        // an arbitrary number of runtime definitions. Every successful lookup
        // is a real zclap event, followed by mandatory final validation.
        for command in &self.commands {
            let mut parser = command.parse(&argv);
            if let Ok(Some(Event::Flag { arg })) = parser.next()
                && parser.next().ok().flatten().is_none()
                && parser.finish().is_ok()
            {
                let index: usize = arg.parse().ok()?;
                return self.targets.get(index).copied();
            }
        }
        None
    }
}

fn syntax(
    kind: &'static str,
    spelling: &[u8],
    spec: Option<&Spec>,
    nargs: i64,
    message: String,
) -> ParseError {
    ParseError {
        kind,
        option: spelling.to_vec(),
        id: spec.map(|s| s.id),
        nargs,
        message,
    }
}

/// Parse without resolving defaults, converting Python values, or invoking user code.
/// Those operations must dispatch through Python's overridable public methods.
pub fn parse<'a>(
    specs: &[Spec],
    argv: &'a [Vec<u8>],
    interspersed: bool,
    ignore_unknown: bool,
) -> ParseResult<'a> {
    let mut spellings = BTreeMap::new();
    let mut prefixes = vec![b"-".to_vec(), b"--".to_vec()];
    for (i, spec) in specs.iter().enumerate() {
        for option in &spec.options {
            let (n, _) = split_prefix(option);
            if n != 0 && !prefixes.iter().any(|p| p == &option[..n]) {
                prefixes.push(option[..n].to_vec());
            }
            if let Some(&b) = option.first() {
                let first = codepoint_len(b).min(option.len());
                if !prefixes.iter().any(|p| p == &option[..first]) {
                    prefixes.push(option[..first].to_vec());
                }
            }
            spellings.insert(encode_spelling(option, is_short(option)), i);
        }
    }
    let names: Vec<_> = spellings.keys().cloned().collect();
    let ids: Vec<_> = (0..names.len()).map(|i| i.to_string()).collect();
    let args: Vec<_> = names
        .iter()
        .zip(&ids)
        .map(|(name, id)| Arg::flag(id).long(name).repeat())
        .collect();
    let kernel = Kernel {
        commands: args
            .chunks(256)
            .map(|chunk| Command::new("zclick").args(chunk))
            .collect(),
        targets: spellings.values().copied().collect(),
    };
    let mut result = ParseResult::default();
    let mut positional: Vec<Cow<'a, [u8]>> = Vec::new();
    let mut cursor = 0;
    while cursor < argv.len() {
        let token = argv[cursor].as_slice();
        cursor += 1;
        if token == b"--" {
            positional.extend(argv[cursor..].iter().map(|v| Cow::Borrowed(v.as_slice())));
            break;
        }
        let first_len = token
            .first()
            .map_or(0, |b| codepoint_len(*b).min(token.len()));
        let option_like =
            token.len() > first_len && prefixes.iter().any(|p| p == &token[..first_len]);
        if !option_like {
            positional.push(Cow::Borrowed(token));
            if !interspersed {
                positional.extend(argv[cursor..].iter().map(|v| Cow::Borrowed(v.as_slice())));
                break;
            }
            continue;
        }
        let eq = token.iter().position(|&b| b == b'=');
        let head = &token[..eq.unwrap_or(token.len())];
        if let Some(index) = kernel.find(head, false) {
            let spec = &specs[index];
            let attached = eq.map(|p| &token[p + 1..]);
            if let Err(error) = consume(
                spec,
                head,
                attached,
                argv,
                &mut cursor,
                &prefixes,
                &mut result,
            ) {
                result.error = Some(error);
                break;
            }
            continue;
        }
        let (prefix_len, repeated) = split_prefix(token);
        if repeated && prefixes.iter().any(|p| p == &token[..prefix_len]) {
            if ignore_unknown {
                positional.push(Cow::Borrowed(token));
                continue;
            }
            result.error = Some(syntax("unknown_option", head, None, 0, String::new()));
            break;
        }
        let prefix = &token[..first_len];
        let mut offset = first_len;
        let mut unknown = prefix.to_vec();
        while offset < token.len() {
            let len = codepoint_len(token[offset]).min(token.len() - offset);
            let end = offset + len;
            let mut spelling = prefix.to_vec();
            spelling.extend_from_slice(&token[offset..end]);
            offset = end;
            let Some(index) = kernel.find(&spelling, true) else {
                if ignore_unknown {
                    unknown.extend_from_slice(&token[end - len..end]);
                    continue;
                }
                result.error = Some(syntax("unknown_option", &spelling, None, 0, String::new()));
                break;
            };
            let spec = &specs[index];
            let attached = if !spec.is_flag && offset < token.len() {
                Some(&token[offset..])
            } else {
                None
            };
            if let Err(error) = consume(
                spec,
                &spelling,
                attached,
                argv,
                &mut cursor,
                &prefixes,
                &mut result,
            ) {
                result.error = Some(error);
                break;
            }
            if !spec.is_flag {
                break;
            }
        }
        if unknown.len() > prefix.len() {
            positional.push(Cow::Owned(unknown));
        }
        if result.error.is_some() {
            break;
        }
    }
    if result.error.is_some() {
        result.leftovers = positional;
        return result;
    }
    assign_positionals(specs, positional, &mut result);
    result
}

fn consume<'a>(
    spec: &Spec,
    spelling: &[u8],
    attached: Option<&'a [u8]>,
    argv: &'a [Vec<u8>],
    cursor: &mut usize,
    prefixes: &[Vec<u8>],
    result: &mut ParseResult<'a>,
) -> Result<(), ParseError> {
    if spec.is_flag {
        if attached.is_some() {
            return Err(syntax(
                "unexpected_value",
                spelling,
                Some(spec),
                0,
                String::new(),
            ));
        }
        result.values.entry(spec.id).or_default().push(Vec::new());
        result.order.push(spec.id);
        return Ok(());
    }
    let count = usize::try_from(spec.nargs).map_err(|_| {
        syntax(
            "definition",
            spelling,
            Some(spec),
            spec.nargs,
            "negative option arity".into(),
        )
    })?;
    let needed = count.saturating_sub(usize::from(attached.is_some()));
    if attached.is_none() && spec.optional_value {
        let next_is_option = argv.get(*cursor).is_none_or(|t| {
            let n = t.first().map_or(0, |b| codepoint_len(*b).min(t.len()));
            t.len() > n && prefixes.iter().any(|p| p == &t[..n])
        });
        if next_is_option {
            result.values.entry(spec.id).or_default().push(Vec::new());
            result.order.push(spec.id);
            return Ok(());
        }
    }
    if argv.len().saturating_sub(*cursor) < needed {
        return Err(syntax(
            "missing_value",
            spelling,
            Some(spec),
            spec.nargs,
            String::new(),
        ));
    }
    let mut values = Vec::with_capacity(count);
    if let Some(value) = attached {
        values.push(value);
    }
    values.extend(argv[*cursor..*cursor + needed].iter().map(Vec::as_slice));
    *cursor += needed;
    // Values go through zclap's byte input/event path. A terminator shields
    // Click's dash-leading values from zclap's native option-boundary policy.
    validate_raw_values(&values)?;
    result
        .values
        .entry(spec.id)
        .or_default()
        .push(values.into_iter().map(Cow::Borrowed).collect());
    result.order.push(spec.id);
    Ok(())
}

fn validate_raw_values(values: &[&[u8]]) -> Result<(), ParseError> {
    const RAW: Command<'static> = Command::new("values").args(&[Arg::positional("raw").repeat()]);
    let mut tokens = Vec::with_capacity(values.len() + 1);
    tokens.push(&b"--"[..]);
    tokens.extend_from_slice(values);
    let mut parser = RAW.parse_bytes(&tokens);
    while parser
        .next()
        .map_err(|e| syntax("kernel", b"", None, 0, e.to_string()))?
        .is_some()
    {}
    parser
        .finish()
        .map_err(|e| syntax("kernel", b"", None, 0, e.to_string()))
}

fn assign_positionals<'a>(
    specs: &[Spec],
    mut input: Vec<Cow<'a, [u8]>>,
    out: &mut ParseResult<'a>,
) {
    let positional: Vec<_> = specs.iter().filter(|s| s.options.is_empty()).collect();
    let variadic: Vec<_> = positional
        .iter()
        .enumerate()
        .filter(|(_, s)| s.nargs < 0)
        .collect();
    if variadic.len() > 1 {
        out.error = Some(syntax(
            "definition",
            b"",
            None,
            -1,
            "Cannot have two nargs < 0".into(),
        ));
        return;
    }
    let pivot = variadic.first().map(|(i, _)| *i);
    let mut ranges = vec![(0, 0); positional.len()];
    let mut left = 0;
    let mut right = input.len();
    for (i, spec) in positional
        .iter()
        .enumerate()
        .take(pivot.unwrap_or(positional.len()))
    {
        let n = usize::try_from(spec.nargs).unwrap_or(0);
        let end = (left + n).min(right);
        ranges[i] = (left, end);
        left = end;
    }
    if let Some(pivot) = pivot {
        for i in (pivot + 1..positional.len()).rev() {
            let n = usize::try_from(positional[i].nargs).unwrap_or(0);
            let begin = right.saturating_sub(n).max(left);
            ranges[i] = (begin, right);
            right = begin;
        }
        ranges[pivot] = (left, right);
        left = right;
    }
    for (i, spec) in positional.iter().enumerate() {
        let (begin, end) = ranges[i];
        if end > begin && spec.nargs >= 0 && end - begin != spec.nargs as usize {
            out.error = Some(syntax(
                "argument_arity",
                b"",
                Some(spec),
                spec.nargs,
                String::new(),
            ));
            break;
        }
        let values = input[begin..end].to_vec();
        let refs: Vec<_> = values.iter().map(|v| v.as_ref()).collect();
        if let Err(error) = validate_raw_values(&refs) {
            out.error = Some(error);
            break;
        }
        out.values.entry(spec.id).or_default().push(values);
        out.order.push(spec.id);
    }
    if pivot.is_none() {
        out.leftovers = input.split_off(left);
    }
}

/// Eager parameters first; encounter order breaks ties, then declaration order.
pub fn processing_order(eager: &[bool], encounters: &[usize]) -> Vec<usize> {
    let mut first = vec![usize::MAX; eager.len()];
    for (position, &id) in encounters.iter().enumerate() {
        if let Some(slot) = first.get_mut(id)
            && *slot == usize::MAX
        {
            *slot = position;
        }
    }
    let mut indices: Vec<_> = (0..eager.len()).collect();
    indices.sort_by_key(|&i| (!eager[i], first[i], i));
    indices
}

/// Resolve a shared destination without discarding higher-priority sources or
/// callback-injected values. Source ranks are Click 8.5.1 ParameterSource values.
/// An explicit default wins over an implicit default at the same rank.
pub fn select_parameter_value(
    existing_missing: bool,
    existing_source: Option<u8>,
    incoming_source: u8,
    existing_explicit: bool,
    incoming_explicit: bool,
) -> bool {
    if existing_missing {
        return true;
    }
    let Some(existing) = existing_source else {
        return false;
    };
    if incoming_source != existing {
        return incoming_source < existing;
    }
    !(existing == 5 && existing_explicit && !incoming_explicit)
}
