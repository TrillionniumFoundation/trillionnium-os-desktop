#[path = "../../../ui/activation_policy.rs"]
mod policy;

#[test]
fn repeated_unmarked_keydown_does_not_repeat_an_effect() {
    use policy::{ActivationPolicy, ActivationSource, ConfirmKey, InputEvent};
    for key in [ConfirmKey::Enter, ConfirmKey::Space] {
        let mut policy = ActivationPolicy::default();
        let press = InputEvent::ConfirmKey { key, pressed: true, repeat: false, modified: false };
        assert!(policy.begin_frame(true, [press]).allows(ActivationSource::Keyboard));
        assert!(!policy.begin_frame(true, [press]).allows(ActivationSource::Keyboard));
    }
}
