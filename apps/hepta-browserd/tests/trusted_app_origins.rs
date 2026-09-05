use hepta_browserd::product_policy::TrustedAppPolicy;

fn decode_label(value: &str) -> String {
    assert_eq!(value.len() % 2, 0);
    let bytes: Vec<u8> = value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            u8::from_str_radix(std::str::from_utf8(pair).expect("ASCII hex"), 16)
                .expect("valid hex")
        })
        .collect();
    String::from_utf8(bytes).expect("UTF-8 label")
}

#[test]
fn shared_origin_vectors_preserve_publisher_isolation() {
    let vectors = include_str!("../../../contracts/golden/trusted-app-origins.v1.tsv");
    let mut count = 0;
    for line in vectors.lines() {
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let columns: Vec<&str> = line.split('\t').collect();
        assert_eq!(columns.len(), 3);
        let app = decode_label(columns[0]);
        let publisher = decode_label(columns[1]);
        let actual = TrustedAppPolicy::derived_origin(&app, &publisher).ok();
        let expected = if columns[2] == "-" {
            None
        } else {
            Some(columns[2])
        };
        assert_eq!(
            actual.as_deref(),
            expected,
            "app={app:?}, publisher={publisher:?}"
        );
        count += 1;
    }
    assert!(count >= 43);
}
