# D0C-04 handler-output contract

Before canonical response construction, handler output is constrained to one
JSON object or one normative typed error. Object members, aggregate container
items, nesting depth, key bytes and string bytes have independent bounds. This
prevents an internal handler from using the response path as an unbounded
allocation or serialization channel.
