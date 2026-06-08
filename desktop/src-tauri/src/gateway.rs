//! 本地 gateway：托管内嵌 SPA，并将 /api/*、/health 反代到 Host API。
//! 保持与浏览器访问 Host 相同的相对路径与 Cookie 语义。

use std::{
    net::SocketAddr,
    path::PathBuf,
    sync::Arc,
    time::Duration,
};

use tauri::Manager;

use axum::{
    Router,
    body::Body,
    extract::{Request, State, ws::{Message as AxumMessage, WebSocket, WebSocketUpgrade}},
    http::{HeaderName, HeaderValue, Method, StatusCode, header},
    response::{IntoResponse, Response},
    routing::{any, get},
};
use bytes::Bytes;
use futures_util::{SinkExt, StreamExt};
use http_body_util::BodyExt;
use reqwest::header::{HeaderMap as ReqHeaderMap, HeaderName as ReqHeaderName, HeaderValue as ReqHeaderValue};
use tokio::net::TcpListener;
use tokio_tungstenite::{connect_async, tungstenite::Message as WsMessage};
use tower_http::{
    services::{ServeDir, ServeFile},
    trace::TraceLayer,
};
use tracing::{error, info};

pub const GATEWAY_HOST: &str = "127.0.0.1";
pub const GATEWAY_PORT: u16 = 1420;

const HOP_BY_HOP: &[&str] = &[
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
];

#[derive(Clone)]
struct GatewayState {
    upstream: Arc<str>,
    client: reqwest::Client,
}

pub fn spawn_gateway(static_dir: PathBuf, upstream: String) {
    if !static_dir.join("index.html").is_file() {
        eprintln!(
            "gateway: index.html not found at {}",
            static_dir.join("index.html").display()
        );
    }
    std::thread::spawn(move || {
        let runtime = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .expect("gateway runtime");
        runtime.block_on(async {
            if let Err(err) = run_gateway(static_dir, upstream).await {
                eprintln!("gateway stopped: {err}");
            }
        });
    });
}

pub async fn wait_until_ready(timeout: Duration) -> Result<(), String> {
    let deadline = std::time::Instant::now() + timeout;
    let addr = format!("{GATEWAY_HOST}:{GATEWAY_PORT}");
    loop {
        if tokio::net::TcpStream::connect(&addr).await.is_ok() {
            return Ok(());
        }
        if std::time::Instant::now() >= deadline {
            return Err(format!("gateway did not listen on {addr} in time"));
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
}

async fn run_gateway(static_dir: PathBuf, upstream: String) -> Result<(), String> {
    if !static_dir.join("index.html").is_file() {
        return Err(format!(
            "desktop frontend build missing: {}",
            static_dir.join("index.html").display()
        ));
    }

    tracing_subscriber::fmt()
        .with_env_filter("info")
        .with_target(false)
        .init();

    let upstream = upstream.trim_end_matches('/').to_string();
    info!("gateway upstream={upstream} static={}", static_dir.display());

    let state = GatewayState {
        upstream: Arc::from(upstream.as_str()),
        client: reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .build()
            .map_err(|err| err.to_string())?,
    };

    let spa_index = static_dir.join("index.html");
    let static_service = ServeDir::new(static_dir).not_found_service(ServeFile::new(spa_index));

    let app = Router::new()
        .route("/health", any(proxy_http))
        .route("/api/notifications/ws", get(proxy_ws))
        .route("/api/{*path}", any(proxy_http))
        .fallback_service(static_service)
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let addr = SocketAddr::from(([127, 0, 0, 1], GATEWAY_PORT));
    let listener = TcpListener::bind(addr)
        .await
        .map_err(|err| format!("bind {addr}: {err}"))?;
    info!("gateway listening on http://{GATEWAY_HOST}:{GATEWAY_PORT}");
    axum::serve(listener, app)
        .await
        .map_err(|err| err.to_string())
}

fn upstream_url(state: &GatewayState, uri: &axum::http::Uri) -> String {
    let path = uri.path_and_query().map(|pq| pq.as_str()).unwrap_or("/");
    format!("{}{path}", state.upstream)
}

fn is_sec_websocket_header(name: &str) -> bool {
    name.len() >= 14 && name.as_bytes()[..14].eq_ignore_ascii_case(b"sec-websocket-")
}

fn should_skip_request_header(name: &str, for_ws_upstream: bool) -> bool {
    if name.eq_ignore_ascii_case("host") {
        return true;
    }
    if HOP_BY_HOP
        .iter()
        .any(|hop| name.eq_ignore_ascii_case(hop))
    {
        return true;
    }
    // 上游 WS 需自行完成握手，不能复用浏览器侧的 Sec-WebSocket-*。
    if for_ws_upstream && is_sec_websocket_header(name) {
        return true;
    }
    false
}

fn copy_request_headers(src: &axum::http::HeaderMap, dst: &mut ReqHeaderMap) {
    copy_request_headers_for(src, dst, false);
}

fn copy_request_headers_for(
    src: &axum::http::HeaderMap,
    dst: &mut ReqHeaderMap,
    for_ws_upstream: bool,
) {
    for (name, value) in src.iter() {
        let name_str = name.as_str();
        if should_skip_request_header(name_str, for_ws_upstream) {
            continue;
        }
        if let (Ok(req_name), Ok(req_value)) = (
            ReqHeaderName::from_bytes(name.as_str().as_bytes()),
            ReqHeaderValue::from_bytes(value.as_bytes()),
        ) {
            dst.insert(req_name, req_value);
        }
    }
}

fn copy_response_headers(src: &ReqHeaderMap, dst: &mut axum::http::HeaderMap) {
    for (name, value) in src.iter() {
        let name_str = name.as_str();
        if HOP_BY_HOP
            .iter()
            .any(|hop| name_str.eq_ignore_ascii_case(hop))
        {
            continue;
        }
        if let (Ok(header_name), Ok(header_value)) = (
            HeaderName::from_bytes(name.as_str().as_bytes()),
            HeaderValue::from_bytes(value.as_bytes()),
        ) {
            dst.insert(header_name, header_value);
        }
    }
}

async fn read_body(req: Request) -> Result<Bytes, StatusCode> {
    req.into_body()
        .collect()
        .await
        .map(|collected| collected.to_bytes())
        .map_err(|_| StatusCode::BAD_REQUEST)
}

async fn proxy_http(
    State(state): State<GatewayState>,
    req: Request,
) -> Result<Response, StatusCode> {
    let method = req.method().clone();
    let headers = req.headers().clone();
    let target = upstream_url(&state, req.uri());
    let body = read_body(req).await?;

    let mut upstream_headers = ReqHeaderMap::new();
    copy_request_headers(&headers, &mut upstream_headers);

    let mut builder = state.client.request(method.clone(), target);
    builder = builder.headers(upstream_headers);
    if !body.is_empty() || method == Method::POST || method == Method::PUT || method == Method::PATCH {
        builder = builder.body(body);
    }

    let upstream = builder
        .send()
        .await
        .map_err(|_| StatusCode::BAD_GATEWAY)?;

    let status = StatusCode::from_u16(upstream.status().as_u16()).unwrap_or(StatusCode::BAD_GATEWAY);
    let mut response_headers = axum::http::HeaderMap::new();
    copy_response_headers(upstream.headers(), &mut response_headers);

    // SSE 使用 chunked 传输，无 Content-Length；若整包缓冲会导致聊天流式输出一次性到达。
    let is_sse = upstream
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|v| v.starts_with("text/event-stream"));

    if is_sse || !upstream.headers().contains_key(header::CONTENT_LENGTH) {
        let stream = upstream.bytes_stream();
        let body = Body::from_stream(stream);
        let mut response = Response::new(body);
        *response.status_mut() = status;
        *response.headers_mut() = response_headers;
        return Ok(response);
    }

    let bytes = upstream
        .bytes()
        .await
        .map_err(|_| StatusCode::BAD_GATEWAY)?;
    let mut response = Response::new(Body::from(bytes));
    *response.status_mut() = status;
    *response.headers_mut() = response_headers;
    Ok(response)
}

async fn proxy_ws(
    ws: WebSocketUpgrade,
    State(state): State<GatewayState>,
    req: Request,
) -> impl IntoResponse {
    let target_http = upstream_url(&state, req.uri());
    let target_ws = target_http
        .replacen("http://", "ws://", 1)
        .replacen("https://", "wss://", 1);
    let headers = req.headers().clone();

    ws.on_upgrade(move |client| async move {
        if let Err(err) = bridge_websocket(client, &target_ws, &headers).await {
            error!("websocket proxy failed: {err}");
        }
    })
}

async fn bridge_websocket(
    mut client: WebSocket,
    target: &str,
    headers: &axum::http::HeaderMap,
) -> Result<(), String> {
    use tokio_tungstenite::tungstenite::client::IntoClientRequest;

    let mut request = target
        .into_client_request()
        .map_err(|err| err.to_string())?;
    copy_request_headers_for(headers, request.headers_mut(), true);

    let (upstream, _resp) = connect_async(request)
        .await
        .map_err(|err| format!("connect {target}: {err}"))?;

    let (mut upstream_tx, mut upstream_rx) = upstream.split();

    loop {
        tokio::select! {
            from_client = client.recv() => {
                match from_client {
                    Some(Ok(AxumMessage::Text(text))) => {
                        upstream_tx.send(WsMessage::Text(text.to_string().into())).await.map_err(|err| err.to_string())?;
                    }
                    Some(Ok(AxumMessage::Binary(data))) => {
                        upstream_tx.send(WsMessage::Binary(data)).await.map_err(|err| err.to_string())?;
                    }
                    Some(Ok(AxumMessage::Ping(payload))) => {
                        upstream_tx.send(WsMessage::Ping(payload)).await.map_err(|err| err.to_string())?;
                    }
                    Some(Ok(AxumMessage::Pong(payload))) => {
                        upstream_tx.send(WsMessage::Pong(payload)).await.map_err(|err| err.to_string())?;
                    }
                    Some(Ok(AxumMessage::Close(_))) | None => break,
                    Some(Err(err)) => return Err(err.to_string()),
                }
            }
            from_upstream = upstream_rx.next() => {
                match from_upstream {
                    Some(Ok(WsMessage::Text(text))) => {
                        client.send(AxumMessage::Text(text.to_string().into())).await.map_err(|err| err.to_string())?;
                    }
                    Some(Ok(WsMessage::Binary(data))) => {
                        client.send(AxumMessage::Binary(data)).await.map_err(|err| err.to_string())?;
                    }
                    Some(Ok(WsMessage::Ping(payload))) => {
                        client.send(AxumMessage::Ping(payload)).await.map_err(|err| err.to_string())?;
                    }
                    Some(Ok(WsMessage::Pong(payload))) => {
                        client.send(AxumMessage::Pong(payload)).await.map_err(|err| err.to_string())?;
                    }
                    Some(Ok(WsMessage::Close(_))) | None => break,
                    Some(Ok(WsMessage::Frame(_))) => {}
                    Some(Err(err)) => return Err(err.to_string()),
                }
            }
        }
    }

    let _ = client.close().await;
    Ok(())
}

pub fn resolve_static_dir(app: &tauri::AppHandle) -> PathBuf {
    use tauri::path::BaseDirectory;

    if cfg!(debug_assertions) {
        let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../frontend/dist-desktop");
        if dev.join("index.html").is_file() {
            return dev;
        }
    }

    app.path()
        .resolve("dist-desktop", BaseDirectory::Resource)
        .unwrap_or_else(|_| PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../frontend/dist-desktop"))
}
