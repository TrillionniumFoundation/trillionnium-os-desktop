use crate::{AnyError, SOCKET_PATH, invalid};
use hepta_agent_transport::{ClientConnection, PeerIdentity, PeerPolicy};
use hepta_browser_codec::{
    BrowserErrorCode, BrowserRequest, BrowserResponse, JsonObject, decode_response, encode_request,
};
use std::os::unix::net::UnixStream;
use std::time::Duration;

const TIMEOUT: Duration = Duration::from_secs(15);

pub(crate) fn invoke(request: BrowserRequest) -> Result<BrowserResponse, AnyError> {
    let stream = UnixStream::connect(SOCKET_PATH)?;
    let server = PeerIdentity::from_stream(&stream)?;
    let mut connection = ClientConnection::connect(stream, PeerPolicy::exact(server), TIMEOUT)?;
    let sequence = connection.send_request(encode_request(&request)?, TIMEOUT)?;
    let decoded = decode_response(&connection.receive_response(sequence, TIMEOUT)?)?.value;
    if decoded.request_id != request.request_id
        || decoded.session_id != request.session_id
        || decoded.session_generation != request.session_generation
    {
        return Err(invalid("response identity drifted from request").into());
    }
    Ok(decoded)
}

pub(crate) fn success<'a>(
    response: &'a BrowserResponse,
    operation: &str,
) -> Result<&'a JsonObject, AnyError> {
    response.outcome.as_ref().map_err(|error| {
        invalid(format!(
            "{operation} failed with {}: {}",
            error.code.as_str(),
            error.message
        ))
        .into()
    })
}

pub(crate) fn error(
    response: &BrowserResponse,
    expected: BrowserErrorCode,
    operation: &str,
) -> Result<(), AnyError> {
    match &response.outcome {
        Err(error) if error.code == expected => Ok(()),
        Err(error) => Err(invalid(format!(
            "{operation} returned {}, expected {}",
            error.code.as_str(),
            expected.as_str()
        ))
        .into()),
        Ok(_) => Err(invalid(format!("{operation} unexpectedly succeeded")).into()),
    }
}
