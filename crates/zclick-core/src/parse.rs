use alloc::{
    borrow::Cow,
    collections::BTreeMap,
    string::{String, ToString},
    vec,
    vec::Vec,
};
use zclap::{Arg, Command, Event};

/// A parsed value retains its argument index, so bindings can preserve object
/// identity without copying bytes or maintaining a pointer-address map.
#[derive(Clone, Debug)]
pub enum ParsedValue<'a> {
    Original { index: usize, bytes: &'a [u8] },
    Slice(&'a [u8]),
    Owned(Vec<u8>),
}
impl ParsedValue<'_> {
    pub fn original_index(&self) -> Option<usize> {
        match self {
            Self::Original { index, .. } => Some(*index),
            _ => None,
        }
    }
}
impl AsRef<[u8]> for ParsedValue<'_> {
    fn as_ref(&self) -> &[u8] {
        match self {
            Self::Original { bytes, .. } | Self::Slice(bytes) => bytes,
            Self::Owned(bytes) => bytes,
        }
    }
}
impl core::ops::Deref for ParsedValue<'_> {
    type Target = [u8];
    fn deref(&self) -> &[u8] {
        self.as_ref()
    }
}

/// The common flag and single-value cases do not allocate an occurrence vector.
#[derive(Debug)]
pub enum OccurrenceValues<'a> {
    Empty,
    One(ParsedValue<'a>),
    Many(Vec<ParsedValue<'a>>),
}
impl<'a> AsRef<[ParsedValue<'a>]> for OccurrenceValues<'a> {
    fn as_ref(&self) -> &[ParsedValue<'a>] {
        match self {
            Self::Empty => &[],
            Self::One(value) => core::slice::from_ref(value),
            Self::Many(values) => values,
        }
    }
}
impl<'a> OccurrenceValues<'a> {
    fn into_vec(self) -> Vec<ParsedValue<'a>> {
        match self {
            Self::Empty => Vec::new(),
            Self::One(value) => vec![value],
            Self::Many(values) => values,
        }
    }
}
#[derive(Debug)]
pub struct Occurrence<'a> {
    pub id: i64,
    pub index: usize,
    pub values: OccurrenceValues<'a>,
}

/// Ordered events are the native execution interface. The map-shaped public
/// result below is assembled only by callers that require that representation.
#[derive(Debug, Default)]
pub struct EventResult<'a> {
    pub events: Vec<Occurrence<'a>>,
    pub leftovers: Vec<ParsedValue<'a>>,
    pub remaining_input: Vec<ParsedValue<'a>>,
    pub error: Option<ParseError>,
}

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
    pub values: BTreeMap<i64, Vec<Vec<ParsedValue<'a>>>>,
    pub leftovers: Vec<ParsedValue<'a>>,
    /// Remaining lexer input before positional assignment, for the legacy mutable-list API.
    pub remaining_input: Vec<ParsedValue<'a>>,
    pub order: Vec<i64>,
    pub error: Option<ParseError>,
}
impl<'a> From<EventResult<'a>> for ParseResult<'a> {
    fn from(events: EventResult<'a>) -> Self {
        let mut result = Self {
            leftovers: events.leftovers,
            remaining_input: events.remaining_input,
            error: events.error,
            ..Self::default()
        };
        for event in events.events {
            result
                .values
                .entry(event.id)
                .or_default()
                .push(event.values.into_vec());
            result.order.push(event.id);
        }
        result
    }
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

// zclap deliberately restricts long spellings to portable identifiers. A
// namespace prefix, with hex framing for uncommon invalid spellings, makes its
// recognizer usable for every Click prefix without changing the Python name. The leading kind separates the
// long and short option namespaces, which Click resolves differently.
fn encode_into(out: &mut String, s: &[u8], short: bool) {
    if let Ok(text) = core::str::from_utf8(s)
        && !s.iter().any(|&b| b <= 32 || b == b'=' || b == 127)
    {
        out.push(if short { 's' } else { 'l' });
        out.push_str(text);
        return;
    }
    const HEX: &[u8; 16] = b"0123456789abcdef";
    out.push(if short { 'S' } else { 'L' });
    for &b in s {
        out.push(HEX[(b >> 4) as usize] as char);
        out.push(HEX[(b & 15) as usize] as char);
    }
}
fn encode_spelling(s: &[u8], short: bool) -> String {
    let mut out = String::with_capacity(s.len() + 1);
    encode_into(&mut out, s, short);
    out
}

fn spelling_hash(bytes: &[u8]) -> usize {
    bytes.iter().fold(0xcbf29ce484222325u64, |hash, &byte| {
        (hash ^ u64::from(byte)).wrapping_mul(0x100000001b3)
    }) as usize
}
struct Recognition {
    names: Vec<String>,
    targets: Vec<usize>,
    buckets: Vec<core::ops::Range<usize>>,
    prefixes: Vec<Vec<u8>>,
}
impl Recognition {
    fn new(specs: &[Spec]) -> Self {
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
        // An owned schema contains names and bucket ranges, never self-referential
        // zclap Commands. A small borrowed candidate table is constructed only
        // when a token visits that bucket. Hashing is not accepted as a match.
        let bucket_count = (spellings.len().max(2) / 2).next_power_of_two();
        let mut entries: Vec<_> = spellings
            .into_iter()
            .map(|(name, target)| {
                let bucket = spelling_hash(name.as_bytes()) & (bucket_count - 1);
                (bucket, name, target)
            })
            .collect();
        entries.sort_unstable_by(|a, b| a.0.cmp(&b.0).then_with(|| a.1.cmp(&b.1)));
        let mut counts = vec![0; bucket_count];
        for &(bucket, _, _) in &entries {
            counts[bucket] += 1;
        }
        let (names, targets) = entries
            .into_iter()
            .map(|(_, name, target)| (name, target))
            .unzip();
        let mut start = 0;
        let buckets = counts
            .into_iter()
            .map(|count| {
                let end = start + count;
                let range = start..end;
                start = end;
                range
            })
            .collect();
        Self {
            names,
            targets,
            buckets,
            prefixes,
        }
    }
}

/// Immutable owned parsing structure, independent of any Python objects or
/// invocation environment. Every zclap borrow is scoped to an actual lookup.
pub struct Schema {
    specs: Vec<Spec>,
    recognition: Recognition,
}
impl Schema {
    pub fn new(specs: Vec<Spec>) -> Self {
        let recognition = Recognition::new(&specs);
        Self { specs, recognition }
    }
    pub fn specs(&self) -> &[Spec] {
        &self.specs
    }
    pub fn parse<'a>(
        &self,
        argv: &[&'a [u8]],
        interspersed: bool,
        ignore_unknown: bool,
        normalizer: Option<Normalizer<'_>>,
    ) -> EventResult<'a> {
        parse_prepared(
            &self.specs,
            &self.recognition,
            argv,
            interspersed,
            ignore_unknown,
            normalizer,
        )
    }
}

struct Kernel<'a> {
    recognition: &'a Recognition,
    token: String,
}
impl Kernel<'_> {
    fn find(&mut self, spelling: &[u8], short: bool) -> Option<usize> {
        self.token.clear();
        self.token.push_str("--");
        encode_into(&mut self.token, spelling, short);
        let argv = [self.token.as_str()];
        let data = self.recognition;
        let bucket = spelling_hash(&self.token.as_bytes()[2..]) & (data.buckets.len() - 1);
        const IDS: [&str; 8] = ["0", "1", "2", "3", "4", "5", "6", "7"];
        let range = data.buckets[bucket].clone();
        for start in (range.start..range.end).step_by(IDS.len()) {
            let count = (range.end - start).min(IDS.len());
            let mut args = [Arg::flag("0"); 8];
            for i in 0..count {
                args[i] = Arg::flag(IDS[i]).long(&data.names[start + i]).repeat();
            }
            let command = Command::new("zclick").args(&args[..count]);
            let mut parser = command.parse(&argv);
            if let Ok(Some(Event::Flag { arg })) = parser.next()
                && parser.next().ok().flatten().is_none()
                && parser.finish().is_ok()
            {
                let index = usize::from(arg.as_bytes()[0] - b'0');
                return data.targets.get(start + index).copied();
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

// A token carries provenance independently of its address. In particular,
// distinct empty Python strings may share one UTF-8 pointer.
#[derive(Clone, Copy)]
struct Token<'a> {
    bytes: &'a [u8],
    original: Option<usize>,
}
impl<'a> From<Token<'a>> for ParsedValue<'a> {
    fn from(token: Token<'a>) -> Self {
        match token.original {
            Some(index) => Self::Original {
                index,
                bytes: token.bytes,
            },
            None => Self::Slice(token.bytes),
        }
    }
}
// One pending slice is sufficient: an attached suffix is consumed before a
// subsequent option can enqueue another suffix.
#[derive(Clone)]
struct Tokens<'v, 'a> {
    argv: &'v [&'a [u8]],
    cursor: usize,
    pending: Option<Token<'a>>,
}
impl<'a> Tokens<'_, 'a> {
    fn peek(&self) -> Option<Token<'a>> {
        self.pending.or_else(|| {
            self.argv.get(self.cursor).map(|&bytes| Token {
                bytes,
                original: Some(self.cursor),
            })
        })
    }
    fn remaining(&self) -> usize {
        self.argv.len() - self.cursor + usize::from(self.pending.is_some())
    }
}
impl<'a> Iterator for Tokens<'_, 'a> {
    type Item = Token<'a>;
    fn next(&mut self) -> Option<Self::Item> {
        if let Some(value) = self.pending.take() {
            return Some(value);
        }
        let &bytes = self.argv.get(self.cursor)?;
        let value = Token {
            bytes,
            original: Some(self.cursor),
        };
        self.cursor += 1;
        Some(value)
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
    parse_with_normalizer(specs, argv, interspersed, ignore_unknown, None)
}

/// Optional caller-owned spelling normalizer. Returning None aborts parsing.
pub type Normalizer<'n> = &'n mut dyn FnMut(&[u8]) -> Option<Vec<u8>>;

fn normalize<'a>(
    normalizer: &mut Option<Normalizer<'_>>,
    spelling: &'a [u8],
) -> Result<Cow<'a, [u8]>, ParseError> {
    match normalizer.as_deref_mut() {
        Some(callback) => callback(spelling)
            .map(Cow::Owned)
            .ok_or_else(|| syntax("normalization", spelling, None, 0, String::new())),
        None => Ok(Cow::Borrowed(spelling)),
    }
}

/// Parse while applying the normalizer at each real long/short lookup attempt.
/// Values are never normalized. The closure may reenter another independent parser.
pub fn parse_with_normalizer<'a>(
    specs: &[Spec],
    argv: &'a [Vec<u8>],
    interspersed: bool,
    ignore_unknown: bool,
    normalizer: Option<Normalizer<'_>>,
) -> ParseResult<'a> {
    let recognition = Recognition::new(specs);
    let argv: Vec<_> = argv.iter().map(Vec::as_slice).collect();
    parse_prepared(
        specs,
        &recognition,
        &argv,
        interspersed,
        ignore_unknown,
        normalizer,
    )
    .into()
}

fn parse_prepared<'a>(
    specs: &[Spec],
    recognition: &Recognition,
    argv: &[&'a [u8]],
    interspersed: bool,
    ignore_unknown: bool,
    mut normalizer: Option<Normalizer<'_>>,
) -> EventResult<'a> {
    let prefixes = &recognition.prefixes;
    let mut kernel = Kernel {
        recognition,
        token: String::with_capacity(64),
    };
    let mut result = EventResult {
        events: Vec::with_capacity(argv.len().max(specs.len())),
        ..EventResult::default()
    };
    let mut positional = Vec::new();
    let mut tokens = Tokens {
        argv,
        cursor: 0,
        pending: None,
    };
    while let Some(source) = tokens.next() {
        let token = source.bytes;
        if token == b"--" {
            result.remaining_input = tokens.clone().map(ParsedValue::from).collect();
            positional.extend(tokens.by_ref().map(ParsedValue::from));
            break;
        }
        let first_len = token
            .first()
            .map_or(0, |b| codepoint_len(*b).min(token.len()));
        let option_like =
            token.len() > first_len && prefixes.iter().any(|p| p == &token[..first_len]);
        if !option_like {
            positional.push(source.into());
            if !interspersed {
                result.remaining_input.push(source.into());
                result
                    .remaining_input
                    .extend(tokens.clone().map(ParsedValue::from));
                positional.extend(tokens.by_ref().map(ParsedValue::from));
                break;
            }
            continue;
        }
        let eq = token.iter().position(|&b| b == b'=');
        let head = &token[..eq.unwrap_or(token.len())];
        let normalized_head = match normalize(&mut normalizer, head) {
            Ok(value) => value,
            Err(error) => {
                result.error = Some(error);
                break;
            }
        };
        if let Some(index) = kernel.find(&normalized_head, false) {
            let spec = &specs[index];
            let attached = eq.map(|p| &token[p + 1..]);
            if let Err(error) = consume(
                index,
                spec,
                &normalized_head,
                attached,
                &mut tokens,
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
                positional.push(source.into());
                continue;
            }
            result.error = Some(syntax(
                "unknown_option",
                &normalized_head,
                None,
                0,
                String::new(),
            ));
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
            let normalized_short = match normalize(&mut normalizer, &spelling) {
                Ok(value) => value,
                Err(error) => {
                    result.error = Some(error);
                    break;
                }
            };
            let Some(index) = kernel.find(&normalized_short, true) else {
                if ignore_unknown {
                    unknown.extend_from_slice(&token[end - len..end]);
                    continue;
                }
                result.error = Some(syntax(
                    "unknown_option",
                    &normalized_short,
                    None,
                    0,
                    String::new(),
                ));
                break;
            };
            let spec = &specs[index];
            let attached = if !spec.is_flag && offset < token.len() {
                Some(&token[offset..])
            } else {
                None
            };
            if let Err(error) = consume(
                index,
                spec,
                &normalized_short,
                attached,
                &mut tokens,
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
        if result.error.is_none() && unknown.len() > prefix.len() {
            positional.push(ParsedValue::Owned(unknown));
        }
        if result.error.is_some() {
            break;
        }
    }
    if result.error.is_some() {
        result.remaining_input = tokens.map(ParsedValue::from).collect();
        result.leftovers = positional;
        return result;
    }
    assign_positionals(specs, positional, &mut result);
    result
}

fn consume<'a>(
    index: usize,
    spec: &Spec,
    spelling: &[u8],
    attached: Option<&'a [u8]>,
    tokens: &mut Tokens<'_, 'a>,
    prefixes: &[Vec<u8>],
    result: &mut EventResult<'a>,
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
        result.events.push(Occurrence {
            id: spec.id,
            index,
            values: OccurrenceValues::Empty,
        });
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
    // Click inserts an attached suffix into the remaining input before applying
    // optional-value rules. It can therefore become an option or positional.
    if let Some(value) = attached {
        tokens.pending = Some(Token {
            bytes: value,
            original: None,
        });
    }
    let available = tokens.remaining();
    let omitted = spec.optional_value
        && (available < count
            || count == 1
                && tokens.peek().is_some_and(|t| {
                    let bytes = t.bytes;
                    let n = bytes
                        .first()
                        .map_or(0, |b| codepoint_len(*b).min(bytes.len()));
                    bytes.len() > n && prefixes.iter().any(|p| p == &bytes[..n])
                }));
    if omitted || count == 0 {
        result.events.push(Occurrence {
            id: spec.id,
            index,
            values: OccurrenceValues::Empty,
        });
        return Ok(());
    }
    if available < count {
        return Err(syntax(
            "missing_value",
            spelling,
            Some(spec),
            spec.nargs,
            String::new(),
        ));
    }
    if count == 1 {
        let value = tokens.next().expect("arity checked before consumption");
        validate_raw_values(&[value.bytes])?;
        result.events.push(Occurrence {
            id: spec.id,
            index,
            values: OccurrenceValues::One(value.into()),
        });
        return Ok(());
    }
    let values: Vec<_> = tokens.take(count).map(ParsedValue::from).collect();
    // Values go through zclap's byte input/event path. A terminator shields
    // Click's dash-leading values from zclap's native option-boundary policy.
    let references: Vec<_> = values.iter().map(AsRef::as_ref).collect();
    validate_raw_values(&references)?;
    result.events.push(Occurrence {
        id: spec.id,
        index,
        values: OccurrenceValues::Many(values),
    });
    Ok(())
}

fn validate_raw_values(values: &[&[u8]]) -> Result<(), ParseError> {
    const RAW: Command<'static> = Command::new("values").args(&[Arg::positional("raw").repeat()]);
    if values.len() == 1 {
        let tokens = [&b"--"[..], values[0]];
        let mut parser = RAW.parse_bytes(&tokens);
        while parser
            .next()
            .map_err(|e| syntax("kernel", b"", None, 0, e.to_string()))?
            .is_some()
        {}
        return parser
            .finish()
            .map_err(|e| syntax("kernel", b"", None, 0, e.to_string()));
    }
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
    mut input: Vec<ParsedValue<'a>>,
    out: &mut EventResult<'a>,
) {
    let positional: Vec<_> = specs
        .iter()
        .enumerate()
        .filter(|(_, s)| s.options.is_empty())
        .collect();
    let variadic: Vec<_> = positional
        .iter()
        .enumerate()
        .filter(|(_, (_, s))| s.nargs < 0)
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
    for (i, (_, spec)) in positional
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
            let n = usize::try_from(positional[i].1.nargs).unwrap_or(0);
            let begin = right.saturating_sub(n).max(left);
            ranges[i] = (begin, right);
            right = begin;
        }
        ranges[pivot] = (left, right);
        left = right;
    }
    for (i, &(index, spec)) in positional.iter().enumerate() {
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
        let values = if values.is_empty() {
            OccurrenceValues::Empty
        } else if values.len() == 1 {
            OccurrenceValues::One(values.into_iter().next().expect("one positional value"))
        } else {
            OccurrenceValues::Many(values)
        };
        out.events.push(Occurrence {
            id: spec.id,
            index,
            values,
        });
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
