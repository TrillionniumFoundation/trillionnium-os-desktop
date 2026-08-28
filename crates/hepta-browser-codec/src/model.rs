use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::net::Ipv6Addr;
use std::str::FromStr;

use sha2::{Digest, Sha256};

use crate::json::{JsonError, JsonObject, JsonValue, decode_unique};
use crate::{BROWSER_API_PROTOCOL, MAX_MESSAGE_BYTES};

const MAX_IDENTIFIER_BYTES: usize = 128;
const MAX_URL_BYTES: usize = 8_192;
const MAX_TYPED_TEXT_BYTES: usize = 131_072;
const MAX_SELECT_BYTES: usize = 65_536;
const MAX_WAIT_TEXT_BYTES: usize = 65_536;
const MAX_ERROR_MESSAGE_BYTES: usize = 1_024;

include!("model/request.rs");
include!("model/types.rs");
include!("model/response.rs");
include!("model/codec.rs");
include!("model/validation.rs");
include!("model/error.rs");
