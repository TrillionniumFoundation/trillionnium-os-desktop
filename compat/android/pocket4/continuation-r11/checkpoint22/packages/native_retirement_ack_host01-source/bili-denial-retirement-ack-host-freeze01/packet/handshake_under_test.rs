//! Exact production capability predicate; no socket or Android activity.
use droidloom_denial_protocol::{capability, DenialMessage, PROTOCOL_MAJOR, RETIREMENT_PROTOCOL_MINOR};
fn qualified_capabilities(message: &DenialMessage) -> Result<(bool, bool), String> {
    match message {
        DenialMessage::ServerHello { major, minor, capabilities, .. }
            if *major == PROTOCOL_MAJOR
                && *minor >= RETIREMENT_PROTOCOL_MINOR
                && capabilities & capability::REQUIRED_V1 == capability::REQUIRED_V1
                && capabilities & capability::TASK_RETIREMENT_ACK != 0 =>
        {
            Ok((capabilities & capability::TASK_ACTIVATION != 0, true))
        }
        DenialMessage::Error { message, .. } => {
            Err(format!("Denial rejected handshake: {message}"))
        }
        _ => Err("Denial handshake lacks qualified retirement receipts".to_owned()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn hello(minor:u16,capabilities:u64)->DenialMessage {
        DenialMessage::ServerHello{major:PROTOCOL_MAJOR,minor,capabilities,
            max_task_objects:64,max_buffers_per_task:64,max_damage_rects:16}
    }
    #[test]
    fn current_minor_and_capability_are_both_required() {
        for minor in 0..RETIREMENT_PROTOCOL_MINOR {
            assert!(qualified_capabilities(&hello(minor,capability::REQUIRED_V1|capability::TASK_RETIREMENT_ACK)).is_err());
        }
        assert!(qualified_capabilities(&hello(RETIREMENT_PROTOCOL_MINOR,capability::REQUIRED_V1)).is_err());
        assert_eq!(qualified_capabilities(&hello(RETIREMENT_PROTOCOL_MINOR,
            capability::REQUIRED_V1|capability::TASK_RETIREMENT_ACK)).unwrap(),(false,true));
    }
    #[test]
    fn activation_is_independent_and_does_not_replace_retirement() {
        assert!(qualified_capabilities(&hello(RETIREMENT_PROTOCOL_MINOR,
            capability::REQUIRED_V1|capability::TASK_ACTIVATION)).is_err());
        assert_eq!(qualified_capabilities(&hello(RETIREMENT_PROTOCOL_MINOR,
            capability::REQUIRED_V1|capability::TASK_ACTIVATION|capability::TASK_RETIREMENT_ACK)).unwrap(),(true,true));
    }
    #[test]
    fn incomplete_base_capabilities_are_rejected() {
        assert!(qualified_capabilities(&hello(RETIREMENT_PROTOCOL_MINOR,capability::TASK_RETIREMENT_ACK)).is_err());
    }
    #[test]
    fn wrong_major_or_unexpected_message_cannot_enable_retirement() {
        let mut message=hello(RETIREMENT_PROTOCOL_MINOR,capability::REQUIRED_V1|capability::TASK_RETIREMENT_ACK);
        if let DenialMessage::ServerHello{major,..}=&mut message{*major+=1;}
        assert!(qualified_capabilities(&message).is_err());
        assert!(qualified_capabilities(&DenialMessage::Ping{cookie:1}).is_err());
    }
}
