// SPDX-License-Identifier: MPL-2.0

use ostd::prelude::ktest;

use super::*;

fn inventory() -> (usize, usize, u64) {
    let graph = GRAPH.disable_irq().lock();
    (
        graph.nodes.iter().filter(|node| node.live).count(),
        graph
            .edges
            .iter()
            .filter(|edge| edge.references != 0)
            .count(),
        graph
            .edges
            .iter()
            .map(|edge| u64::from(edge.references))
            .sum(),
    )
}

#[ktest]
fn real_graph_aliases_keep_edges_until_final_lease_and_reject_stale_generation() {
    let before = inventory();
    let source = Node::new().unwrap();
    let target = Node::new().unwrap();
    let stale = target.0.id;
    let weak = Arc::downgrade(&target.0);
    let edge = Lease::single(&source, &target).unwrap();
    let alias = edge.clone();
    assert_eq!(
        Lease::single(&target, &source).unwrap_err().error(),
        Errno::ELOOP
    );
    drop((edge, target));
    assert!(weak.upgrade().is_some());
    drop(alias);
    assert!(weak.upgrade().is_none());
    let replacement = Node::new().unwrap();
    assert!(!GRAPH.disable_irq().lock().valid(stale));
    drop((source, replacement));
    assert_eq!(inventory(), before);
}

#[ktest]
fn actual_node_capacity_fails_closed_and_refunds_registration() {
    let before = inventory();
    let mut nodes = Vec::new();
    loop {
        match Node::new() {
            Ok(node) => nodes.push(node),
            Err(error) => {
                assert_eq!(error.error(), Errno::ENOBUFS);
                break;
            }
        }
    }
    assert_eq!(inventory().0, MAX_NODES);
    assert_eq!(nodes.len() + before.0, MAX_NODES);
    drop(nodes);
    assert_eq!(inventory(), before);
}

#[ktest]
fn actual_edge_capacity_rolls_back_unpublished_batch_and_duplicate_reference() {
    let before = inventory();
    let sources = (0..65).map(|_| Node::new().unwrap()).collect::<Vec<_>>();
    let targets = (0..65).map(|_| Node::new().unwrap()).collect::<Vec<_>>();
    let mut leases = Vec::new();
    let mut failure = None;
    'outer: for (si, source) in sources.iter().enumerate() {
        for (ti, target) in targets.iter().enumerate() {
            match Lease::single(source, target) {
                Ok(edge) => leases.push(edge),
                Err(error) => {
                    assert_eq!(error.error(), Errno::ENOBUFS);
                    failure = Some((si, ti));
                    break 'outer;
                }
            }
        }
    }
    assert!(failure.is_some());
    assert_eq!(inventory().1, MAX_EDGES);
    // Re-add an existing edge, then fail on an unallocated one in the same
    // transaction. Rollback must restore its reference count as well.
    let fresh = Node::new().unwrap();
    let full = inventory();
    assert_eq!(
        Lease::new(&sources[0], vec![targets[0].clone(), fresh.clone()])
            .unwrap_err()
            .error(),
        Errno::ENOBUFS
    );
    assert_eq!(inventory(), full);
    drop((leases, sources, targets, fresh));
    assert_eq!(inventory(), before);
}
