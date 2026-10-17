// Reproducer linked against os-control at commit
// 51327db35f6e51c1818b59274275a022b7248efc, before a depth limit.
use os_control::{ResourceDomain, ResourceDomainId, StableObjectId};

fn main() {
    let depth: usize = std::env::args().nth(1).unwrap().parse().unwrap();
    let stack: usize = std::env::args().nth(2).unwrap().parse().unwrap();
    std::thread::Builder::new()
        .stack_size(stack)
        .spawn(move || {
            let mut leaf = ResourceDomain::new(
                ResourceDomainId::from_u128(1),
                StableObjectId::from_u128(1),
                None,
                1,
            )
            .unwrap();
            for id in 2..=(depth as u128) {
                leaf = ResourceDomain::new(
                    ResourceDomainId::from_u128(id),
                    StableObjectId::from_u128(id),
                    Some(&leaf),
                    1,
                )
                .unwrap();
            }
            eprintln!("constructed {depth} domains on {stack}-byte stack; dropping final handle");
            drop(leaf);
            eprintln!("drop complete");
        })
        .unwrap()
        .join()
        .unwrap();
}
