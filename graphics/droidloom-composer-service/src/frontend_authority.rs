//! A synchronous Binder transaction and root UID are only an entry precheck.
//! Actual endpoint role, creator PID and lifetime are verified by KernelCaller.

#[derive(Clone, Copy)]
pub(crate) enum Endpoint {
    Input,
    TaskControl,
}

pub(crate) fn permitted(handling_transaction: bool, uid: u32) -> bool {
    handling_transaction && uid == 0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn synchronous_root_transaction_passes_only_the_precheck() {
        assert!(permitted(true, 0));
    }

    #[test]
    fn uid_or_execution_outside_a_transaction_fails_the_precheck() {
        assert!(!permitted(false, 0));
        assert!(!permitted(true, 1000));
        assert!(!permitted(false, 1000));
    }
}
