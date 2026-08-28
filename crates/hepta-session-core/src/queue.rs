//! Bounded FIFO admission queue for Agent and human control operations.

use std::collections::VecDeque;
use std::error::Error;
use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QueueError {
    ZeroCapacity,
    Full { capacity: usize },
}

impl fmt::Display for QueueError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::ZeroCapacity => formatter.write_str("queue capacity must be positive"),
            Self::Full { capacity } => write!(formatter, "queue is full at capacity {capacity}"),
        }
    }
}

impl Error for QueueError {}

#[derive(Debug, Clone)]
pub struct ArbiterQueue<T> {
    capacity: usize,
    entries: VecDeque<T>,
}

impl<T> ArbiterQueue<T> {
    pub fn new(capacity: usize) -> Result<Self, QueueError> {
        if capacity == 0 {
            return Err(QueueError::ZeroCapacity);
        }
        Ok(Self {
            capacity,
            entries: VecDeque::with_capacity(capacity),
        })
    }

    pub fn push(&mut self, item: T) -> Result<(), QueueError> {
        if self.entries.len() >= self.capacity {
            return Err(QueueError::Full {
                capacity: self.capacity,
            });
        }
        self.entries.push_back(item);
        Ok(())
    }

    pub fn pop(&mut self) -> Option<T> {
        self.entries.pop_front()
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub const fn capacity(&self) -> usize {
        self.capacity
    }
}
