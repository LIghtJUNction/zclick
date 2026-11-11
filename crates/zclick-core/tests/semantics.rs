use zclick_core::{
    Spec, parse, processing_order, strip_ansi, text_width, truncate_visible, wrap_text,
};
fn option(id: i64, names: &[&str], nargs: i64, flag: bool) -> Spec {
    Spec {
        id,
        options: names.iter().map(|s| s.as_bytes().to_vec()).collect(),
        nargs,
        is_flag: flag,
        optional_value: false,
    }
}
fn argv(values: &[&str]) -> Vec<Vec<u8>> {
    values.iter().map(|s| s.as_bytes().to_vec()).collect()
}
fn raw(result: &zclick_core::ParseResult<'_>, id: i64) -> Vec<Vec<Vec<u8>>> {
    result.values[&id]
        .iter()
        .map(|v| v.iter().map(|s| s.to_vec()).collect())
        .collect()
}
#[test]
fn real_kernel_long_short_clusters_and_dash_values() {
    let specs = [
        option(0, &["-v", "--verbose"], 1, true),
        option(1, &["-n", "--number"], 1, false),
        option(2, &[], 1, false),
    ];
    let args = argv(&["-vvn-12", "--number", "--verbose", "file"]);
    let parsed = parse(&specs, &args, true, false);
    assert!(parsed.error.is_none());
    assert_eq!(parsed.order, [0, 0, 1, 1, 2]);
    assert_eq!(
        raw(&parsed, 1),
        vec![vec![b"-12".to_vec()], vec![b"--verbose".to_vec()]]
    );
    assert_eq!(raw(&parsed, 2), vec![vec![b"file".to_vec()]]);
}
#[test]
fn short_equal_is_part_of_value_and_long_equal_is_separator() {
    let specs = [option(0, &["-n", "--number"], 1, false)];
    let args = argv(&["-n=2", "--number=3"]);
    let parsed = parse(&specs, &args, true, false);
    assert_eq!(
        raw(&parsed, 0),
        vec![vec![b"=2".to_vec()], vec![b"3".to_vec()]]
    );
}
#[test]
fn negative_values_and_terminator_are_preserved() {
    let specs = [option(0, &["--pair"], 2, false), option(1, &[], -1, false)];
    let args = argv(&["--pair", "-1", "--", "--", "-x", ""]);
    let result = parse(&specs, &args, true, false);
    assert!(result.error.is_none());
    assert_eq!(raw(&result, 0), vec![vec![b"-1".to_vec(), b"--".to_vec()]]);
    assert_eq!(raw(&result, 1), vec![vec![b"-x".to_vec(), Vec::new()]]);
}
#[test]
fn unknown_short_cluster_is_reassembled_and_can_be_positional() {
    let specs = [option(0, &["-v"], 1, true), option(1, &[], -1, false)];
    let args = argv(&["-avb", "--unknown=3"]);
    let result = parse(&specs, &args, true, true);
    assert!(result.error.is_none());
    assert_eq!(result.order, [0, 1]);
    assert_eq!(
        raw(&result, 1),
        vec![vec![b"-ab".to_vec(), b"--unknown=3".to_vec()]]
    );
}
#[test]
fn arbitrary_prefix_and_spelling_roundtrip() {
    let specs = [
        option(0, &["+v", "/verbose", "!空 白"], 1, true),
        option(1, &["++n"], 1, false),
    ];
    let args = argv(&["+v", "/verbose", "!空 白", "++n=-1"]);
    let result = parse(&specs, &args, true, false);
    assert!(result.error.is_none());
    assert_eq!(result.order, [0, 0, 0, 1]);
    assert_eq!(raw(&result, 1), vec![vec![b"-1".to_vec()]]);
}
#[test]
fn optional_value_defers_when_next_is_option() {
    let mut s = option(0, &["--name"], 1, false);
    s.optional_value = true;
    let specs = [s, option(1, &["--flag"], 1, true)];
    let args = argv(&["--name", "--flag"]);
    let result = parse(&specs, &args, true, false);
    assert!(result.error.is_none());
    assert_eq!(raw(&result, 0), vec![Vec::<Vec<u8>>::new()]);
    assert_eq!(result.order, [0, 1]);
}
#[test]
fn option_arity_errors_keep_prior_events() {
    let specs = [
        option(0, &["-v"], 1, true),
        option(1, &["--pair"], 2, false),
    ];
    let args = argv(&["-v", "--pair", "a"]);
    let result = parse(&specs, &args, true, false);
    assert_eq!(result.order, [0]);
    assert_eq!(result.error.unwrap().kind, "missing_value");
}
#[test]
fn variadic_before_fixed_uses_right_hand_assignment() {
    let specs = [
        option(0, &[], 1, false),
        option(1, &[], -1, false),
        option(2, &[], 2, false),
    ];
    let args = argv(&["a", "b", "c", "d", "e"]);
    let result = parse(&specs, &args, true, false);
    assert!(result.error.is_none());
    assert_eq!(raw(&result, 0), vec![vec![b"a".to_vec()]]);
    assert_eq!(raw(&result, 1), vec![vec![b"b".to_vec(), b"c".to_vec()]]);
    assert_eq!(raw(&result, 2), vec![vec![b"d".to_vec(), b"e".to_vec()]]);
}
#[test]
fn missing_positionals_are_empty_occurrences() {
    let specs = [option(0, &[], 1, false), option(1, &[], -1, false)];
    let args = Vec::new();
    let result = parse(&specs, &args, true, false);
    assert!(result.error.is_none());
    assert_eq!(result.order, [0, 1]);
    assert_eq!(raw(&result, 0), vec![Vec::<Vec<u8>>::new()]);
    assert_eq!(raw(&result, 1), vec![Vec::<Vec<u8>>::new()]);
}
#[test]
fn stop_at_first_argument_keeps_child_options() {
    let specs = [option(0, &["--flag"], 1, true)];
    let args = argv(&["--flag", "child", "--flag"]);
    let result = parse(&specs, &args, false, false);
    assert!(result.error.is_none());
    assert_eq!(result.order, [0]);
    assert_eq!(
        result
            .leftovers
            .iter()
            .map(|v| v.as_ref())
            .collect::<Vec<_>>(),
        [b"child".as_slice(), b"--flag"]
    );
}
#[test]
fn large_dynamic_command_is_not_limited_to_kernel_bitset() {
    let specs: Vec<_> = (0..1025)
        .map(|i| option(i, &[&format!("--item{i}")], 1, false))
        .collect();
    let args = argv(&["--item1024=last", "--item0=first"]);
    let result = parse(&specs, &args, true, false);
    assert!(result.error.is_none());
    assert_eq!(result.order, [1024, 0]);
}
#[test]
fn owned_surrogate_pass_bytes_never_change() {
    let specs = [option(0, &["--name"], 1, false)];
    let raw = vec![0xed, 0xb3, 0xbf];
    let args = vec![b"--name".to_vec(), raw.clone()];
    let result = parse(&specs, &args, true, false);
    assert_eq!(result.values[&0][0][0].as_ref(), raw);
}
#[test]
fn duplicate_spellings_follow_last_definition() {
    let specs = [option(0, &["--a"], 1, true), option(1, &["--a"], 1, true)];
    let args = argv(&["--a"]);
    let result = parse(&specs, &args, true, false);
    assert_eq!(result.order, [1]);
}
#[test]
fn callback_order_obeys_eager_encounter_and_fallback() {
    assert_eq!(
        processing_order(&[false, true, false, true, false], &[2, 0, 2]),
        [1, 3, 2, 0, 4]
    );
}
#[test]
fn ansi_full_csi_and_incomplete_sequences() {
    let text = b"x\x1b[38:2:1:2:3my\x1b[0m\x1b[?25lz\x1b[1;";
    assert_eq!(strip_ansi(text), b"xyz\x1b[1;");
    assert_eq!(text_width("\x1b[31m空é\x1b[0m".as_bytes()), 2);
    assert_eq!(truncate_visible(b"\x1b[31mabc\x1b[0m", 2), b"\x1b[31mab");
}
#[test]
fn wrapped_ansi_layout_matches_plain_and_raw_paragraphs() {
    let styled = wrap_text(b"\x1b[31malpha\x1b[0m beta gamma", 10, b"", b"", false).unwrap();
    let plain = wrap_text(b"alpha beta gamma", 10, b"", b"", false).unwrap();
    assert_eq!(strip_ansi(&styled), plain);
    let raw = wrap_text(b"One paragraph.\n\n\x08\n  A\n   B", 20, b"  ", b"  ", true).unwrap();
    assert_eq!(raw, b"  One paragraph.\n\n    A\n     B");
}
#[test]
fn source_arbitration_preserves_priority_and_user_injections() {
    use zclick_core::select_parameter_value as select;
    assert!(select(true, None, 5, false, false));
    assert!(!select(false, None, 1, false, true));
    for old in 1..=5 {
        for new in 1..=5 {
            assert_eq!(select(false, Some(old), new, true, true), new <= old);
        }
    }
    assert!(!select(false, Some(5), 5, true, false));
    assert!(select(false, Some(5), 5, false, true));
    assert!(select(false, Some(5), 2, true, false));
}
#[test]
fn zero_arity_option_requeues_attached_suffix_without_allocation() {
    let specs = [
        option(0, &["-z", "--zero"], 0, false),
        option(1, &["--flag"], 1, true),
        option(2, &[], -1, false),
    ];
    for tokens in [&["--zero=--flag", "rest"][..], &["-z--flag", "rest"][..]] {
        let args = argv(tokens);
        let result = parse(&specs, &args, true, false);
        assert!(result.error.is_none());
        assert_eq!(result.order, [0, 1, 2]);
        assert_eq!(raw(&result, 0), vec![Vec::<Vec<u8>>::new()]);
        assert_eq!(raw(&result, 2), vec![vec![b"rest".to_vec()]]);
    }
}
