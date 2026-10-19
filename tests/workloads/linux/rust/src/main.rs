use std::error::Error;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{UnixListener, UnixStream};

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() -> Result<(), Box<dyn Error>> {
    let scratch = PathBuf::from(std::env::args().nth(1).ok_or("usage: a04-tokio-workload SCRATCH")?);
    let counter = Arc::new(AtomicUsize::new(0));
    let threads: Vec<_> = (0..4).map(|_| {
        let counter = Arc::clone(&counter);
        std::thread::spawn(move || {
            for _ in 0..1000 { counter.fetch_add(1, Ordering::SeqCst); }
        })
    }).collect();
    for t in threads { t.join().map_err(|_| "std thread panicked")?; }
    if counter.load(Ordering::SeqCst) != 4000 { return Err("std thread mismatch".into()); }

    let socket_path = scratch.join("tokio.sock");
    let listener = UnixListener::bind(&socket_path)?;
    let server = tokio::spawn(async move {
        let (mut conn, _) = listener.accept().await?;
        let mut got = [0; 4];
        conn.read_exact(&mut got).await?;
        if &got != b"ping" { return Err(std::io::Error::other("bad request")); }
        conn.write_all(b"pong").await?;
        Ok::<_, std::io::Error>(())
    });
    let mut client = UnixStream::connect(&socket_path).await?;
    client.write_all(b"ping").await?;
    let mut reply = [0; 4];
    client.read_exact(&mut reply).await?;
    if &reply != b"pong" { return Err("bad reply".into()); }
    server.await??;
    drop(client);
    tokio::fs::remove_file(&socket_path).await?;

    let path = scratch.join("tokio-data");
    tokio::fs::write(&path, b"tokio-io").await?;
    if tokio::fs::read(&path).await? != b"tokio-io" { return Err("async fs mismatch".into()); }
    tokio::fs::remove_file(path).await?;
    let mut handles = Vec::new();
    for i in 0..16 { handles.push(tokio::spawn(async move { tokio::task::yield_now().await; i })); }
    let mut seen = [false; 16];
    for h in handles { seen[h.await?] = true; }
    if !seen.iter().all(|x| *x) { return Err("task completion mismatch".into()); }
    println!("{{\"ok\":true,\"std_threads\":4,\"counter\":4000,\"tokio_tasks\":16,\"unix_socket\":true,\"async_fs\":true}}");
    Ok(())
}
