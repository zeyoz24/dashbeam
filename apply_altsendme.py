#!/usr/bin/env python3 """ apply_altsendme.py Applies the LAN-alias transfer feature to the exact DashBeam repository revision inspected when this script was generated. The supplied altsendme.patch is intentionally ignored and is never applied. """ from __future__ import annotations import datetime as _datetime import os import shutil import subprocess import sys import tempfile from pathlib import Path EXPECTED_HEAD = "bbe532af30015c29d2cf0d96e7779c5716096347" MARKER = "ALT_SENDME_LAN_ALIAS_V1" ALLOWED_DIRTY_PATHS = { "apply_altsendme.py", "altsendme.patch", } NEW_FILES = { "engine/native/src/lan_alias.rs": r'''// ALT_SENDME_LAN_ALIAS_V1 use std::collections::HashMap; use std::fmt; use std::time::{Duration, Instant}; pub const ALIAS_TTL: Duration = Duration::from_secs(15 * 60); pub const ALIAS_MIN_LEN: usize = 4; pub const ALIAS_MAX_LEN: usize = 32; #[derive(Debug, Clone)] struct AliasEntry { blob_ticket: String, registered_at: Instant, } #[derive(Debug, Clone, Copy, PartialEq, Eq)] pub enum AliasError { Invalid, EmptyTicket, Duplicate, NotFound, Expired, } impl fmt::Display for AliasError { fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result { formatter.write_str(match self { Self::Invalid => "invalid alias", Self::EmptyTicket => "blob ticket must not be empty", Self::Duplicate => "alias is already registered", Self::NotFound => "alias was not found", Self::Expired => "alias has expired", }) } } impl std::error::Error for AliasError {} #[derive(Debug, Default)] pub struct LanAliasRegistry { aliases: HashMap<String, AliasEntry>, } impl LanAliasRegistry { pub fn new() -> Self { Self::default() } pub fn normalize_alias(raw: &str) -> Result<String, AliasError> { let trimmed = raw.trim(); if !trimmed.is_ascii() { return Err(AliasError::Invalid); } let normalized = trimmed.to_ascii_lowercase(); if !(ALIAS_MIN_LEN..=ALIAS_MAX_LEN).contains(&normalized.len()) { return Err(AliasError::Invalid); } if !normalized .bytes() .all(|value| value.is_ascii_lowercase() || value.is_ascii_digit() || value == b'_' || value == b'-') { return Err(AliasError::Invalid); } Ok(normalized) } pub fn register(&mut self, alias: &str, blob_ticket: &str) -> Result<(), AliasError> { self.register_at(alias, blob_ticket, Instant::now()) } pub fn resolve(&mut self, alias: &str) -> Result<String, AliasError> { self.resolve_at(alias, Instant::now()) } pub fn clear(&mut self) { self.aliases.clear(); } fn register_at( &mut self, alias: &str, blob_ticket: &str, now: Instant, ) -> Result<(), AliasError> { let normalized = Self::normalize_alias(alias)?; if blob_ticket.trim().is_empty() { return Err(AliasError::EmptyTicket); } self.prune_expired_at(now); if self.aliases.contains_key(&normalized) { return Err(AliasError::Duplicate); } self.aliases.insert( normalized, AliasEntry { blob_ticket: blob_ticket.to_owned(), registered_at: now, }, ); Ok(()) } fn resolve_at(&mut self, alias: &str, now: Instant) -> Result<String, AliasError> { let normalized = Self::normalize_alias(alias)?; let Some(entry) = self.aliases.get(&normalized) else { return Err(AliasError::NotFound); }; if now.saturating_duration_since(entry.registered_at) >= ALIAS_TTL { self.aliases.remove(&normalized); return Err(AliasError::Expired); } Ok(entry.blob_ticket.clone()) } fn prune_expired_at(&mut self, now: Instant) { self.aliases.retain(|_, entry| { now.saturating_duration_since(entry.registered_at) < ALIAS_TTL }); } } #[cfg(test)] mod tests { use super::*; #[test] fn normalization_trims_and_lowercases_ascii() { assert_eq!( LanAliasRegistry::normalize_alias(" MyCode123 ").unwrap(), "mycode123" ); assert_eq!( LanAliasRegistry::normalize_alias("UPPER_CASE-1").unwrap(), "upper_case-1" ); } #[test] fn normalization_rejects_unicode() { for alias in ["café", "日本語", "naïve", "Übung"] { assert_eq!( LanAliasRegistry::normalize_alias(alias), Err(AliasError::Invalid) ); } } #[test] fn normalization_rejects_invalid_characters_and_lengths() { for alias in ["foo", "foo bar", "foo@bar", "test.com", "code#123"] { assert_eq!( LanAliasRegistry::normalize_alias(alias), Err(AliasError::Invalid) ); } assert_eq!( LanAliasRegistry::normalize_alias(&"a".repeat(33)), Err(AliasError::Invalid) ); } #[test] fn empty_ticket_is_rejected() { let mut registry = LanAliasRegistry::new(); assert_eq!( registry.register("alias1", ""), Err(AliasError::EmptyTicket) ); assert_eq!( registry.register("alias2", " "), Err(AliasError::EmptyTicket) ); } #[test] fn duplicate_registration_does_not_overwrite() { let now = Instant::now(); let mut registry = LanAliasRegistry::new(); registry.register_at("SameAlias", "ticket-one", now).unwrap(); assert_eq!( registry.register_at("samealias", "ticket-two", now), Err(AliasError::Duplicate) ); assert_eq!( registry.resolve_at("samealias", now).unwrap(), "ticket-one" ); } #[test] fn expiry_is_deterministic_and_removes_the_entry() { let now = Instant::now(); let mut registry = LanAliasRegistry::new(); registry.register_at("expires", "ticket-one", now).unwrap(); assert_eq!( registry.resolve_at("expires", now + ALIAS_TTL), Err(AliasError::Expired) ); assert_eq!( registry.resolve_at("expires", now + ALIAS_TTL), Err(AliasError::NotFound) ); } #[test] fn registration_prunes_expired_entries_without_sleeping() { let now = Instant::now(); let mut registry = LanAliasRegistry::new(); registry.register_at("first1", "ticket-one", now).unwrap(); registry .register_at("second", "ticket-two", now + ALIAS_TTL) .unwrap(); assert_eq!( registry.resolve_at("first1", now + ALIAS_TTL), Err(AliasError::NotFound) ); assert_eq!( registry.resolve_at("second", now + ALIAS_TTL).unwrap(), "ticket-two" ); } #[test] fn clear_removes_all_aliases() { let mut registry = LanAliasRegistry::new(); registry.register("alias1", "ticket-one").unwrap(); registry.register("alias2", "ticket-two").unwrap(); registry.clear(); assert_eq!(registry.resolve("alias1"), Err(AliasError::NotFound)); assert_eq!(registry.resolve("alias2"), Err(AliasError::NotFound)); } } ''', "frontend/src/lib/lan-alias.ts": r'''// ALT_SENDME_LAN_ALIAS_V1 export const LAN_ALIAS_MIN_LENGTH = 4 export const LAN_ALIAS_MAX_LENGTH = 32 export const LAN_ALIAS_PATTERN = /^[a-z0-9_-]+$/ export type AliasResolutionOutcome = 	| { 			status: 'not_found' 	 } 	| { 			status: 'unique_match' 			blobTicket: string 	 } 	| { 			status: 'ambiguous' 			peers: Array<{ 				endpointId: string 				displayName?: string | null 				fingerprint: string 			}> 	 } 	| { 			status: 'error' 			code: string 			message: string 	 } export type ReceiveInputResolution = 	| { kind: 'raw_ticket'; ticket: string } 	| { kind: 'alias'; alias: string } 	| { kind: 'invalid_alias' } export function normalizeLanAlias(value: string): string | null { 	const normalized = value.trim().toLowerCase() 	if ( 		normalized.length < LAN_ALIAS_MIN_LENGTH || 		normalized.length > LAN_ALIAS_MAX_LENGTH || 		!LAN_ALIAS_PATTERN.test(normalized) 	) { 		return null 	} 	return normalized } export function classifyReceiveInput(value: string): ReceiveInputResolution { 	const trimmed = value.trim() 	if (!trimmed) { 		return { kind: 'raw_ticket', ticket: '' } 	} 	// Blob tickets and receive links are substantially longer than a LAN alias. 	// Short input is therefore treated as an alias attempt so malformed aliases 	// receive a useful validation error instead of a ticket-parser error. 	if (trimmed.length <= LAN_ALIAS_MAX_LENGTH) { 		const alias = normalizeLanAlias(trimmed) 		return alias ? { kind: 'alias', alias } : { kind: 'invalid_alias' } 	} 	return { kind: 'raw_ticket', ticket: trimmed } } ''', "frontend/src/lib/lan-alias.test.ts": r'''import assert from 'node:assert/strict' import test from 'node:test' import { 	classifyReceiveInput, 	normalizeLanAlias, 	type AliasResolutionOutcome, } from './lan-alias.js' test('normalizes aliases without exposing a nonce', () => { 	assert.equal(normalizeLanAlias(' MyCode123 '), 'mycode123') 	assert.equal(normalizeLanAlias('UPPER_CASE-1'), 'upper_case-1') 	assert.equal(normalizeLanAlias('café'), null) 	assert.equal(normalizeLanAlias('bad code'), null) 	assert.equal(normalizeLanAlias('abc'), null) 	assert.equal(normalizeLanAlias('a'.repeat(33)), null) 	const outcome: AliasResolutionOutcome = { 		status: 'unique_match', 		blobTicket: 'ticket', 	} 	assert.deepEqual(Object.keys(outcome).sort(), ['blobTicket', 'status']) 	assert.equal(JSON.stringify(outcome).includes('nonce'), false) }) test('keeps raw ticket and receive-link fallback', () => { 	const rawTicket = `blob${'x'.repeat(100)}` 	assert.deepEqual(classifyReceiveInput(rawTicket), { 		kind: 'raw_ticket', 		ticket: rawTicket, 	}) 	const link = `https://app.dashbeam.net/receive?ticket=${'x'.repeat(100)}` 	assert.deepEqual(classifyReceiveInput(link), { 		kind: 'raw_ticket', 		ticket: link, 	}) }) test('classifies valid aliases before raw-ticket fallback', () => { 	assert.deepEqual(classifyReceiveInput(' MyCode123 '), { 		kind: 'alias', 		alias: 'mycode123', 	}) 	assert.deepEqual(classifyReceiveInput('bad code'), { 		kind: 'invalid_alias', 	}) }) ''', "RELEASE.md": r'''# Android and Windows builds ## Validation Use Rust 1.91 and Node as specified by `.nvmrc`. ```sh cargo fmt --manifest-path engine/Cargo.toml -- --check cargo test --manifest-path engine/Cargo.toml -p sendme-protocol -p sendme-native cargo check --manifest-path engine/Cargo.toml pnpm install --frozen-lockfile pnpm run format:check pnpm run lint pnpm run test:lib pnpm run build cargo check --manifest-path src-tauri/Cargo.toml 

Android

Install JDK 17, Android platform/build-tools 36, NDK r28b, Rust Android
targets, and the Tauri mobile prerequisites. The generated manifest includes
network-state, Wi-Fi-state, and multicast permissions. The native-utils plugin
holds a reference-counted WifiManager.MulticastLock while the device node is
alive so mDNS can receive multicast packets.

Development APK:

pnpm install --frozen-lockfile pnpm tauri android build --debug 

Signed release APKs, using the repository’s existing signing environment:

pnpm run android:build:release 

Test sender and receiver in airplane mode with Wi-Fi re-enabled, on the same
access point or hotspot. Confirm Nearby discovery, alias lookup, raw ticket
receive, receive links, and paired-device invites.

Windows

Build Windows artifacts on Windows with the MSVC Rust target, WebView2, NSIS,
and WiX prerequisites:

pnpm install --frozen-lockfile cargo test --manifest-path engine/Cargo.toml -p sendme-protocol -p sendme-native cargo check --manifest-path src-tauri/Cargo.toml pnpm tauri build --target x86_64-pc-windows-msvc --bundles nsis,msi 

The workflow in .github/workflows/altsendme-platform-build.yml performs
unsigned/manual-review Android and Windows artifact builds. It uploads workflow
artifacts only. It never creates or publishes a GitHub Release.
‘’‘,
“.github/workflows/altsendme-platform-build.yml”: r’''name: AltSendme Android and Windows artifacts

on:
workflow_dispatch:
pull_request:
branches:
- main

permissions:
contents: read

jobs:
windows:
runs-on: windows-latest
timeout-minutes: 90
steps:
- uses: actions/checkout@v5
- uses: pnpm/action-setup@v4
with:
version: 10.12.1
- uses: actions/setup-node@v4
with:
node-version-file: .nvmrc
cache: pnpm
- uses: dtolnay/rust-toolchain@stable
with:
toolchain: ‘1.91’
targets: x86_64-pc-windows-msvc
- name: Install dependencies
run: pnpm install --frozen-lockfile
- name: Test native protocol
run: cargo test --manifest-path engine/Cargo.toml -p sendme-protocol -p sendme-native
- name: Build Windows bundles
run: pnpm tauri build --target x86_64-pc-windows-msvc --bundles nsis
- uses: actions/upload-artifact@v4
with:
name: dashbeam-windows
path: |
src-tauri/target/x86_64-pc-windows-msvc/release/bundle/nsis/**
if-no-files-found: error

android:
runs-on: ubuntu-22.04
timeout-minutes: 180
steps:
- uses: actions/checkout@v5
- uses: pnpm/action-setup@v4
with:
version: 10.12.1
- uses: actions/setup-node@v4
with:
node-version-file: .nvmrc
cache: pnpm
- uses: actions/setup-java@v5
with:
distribution: temurin
java-version: ‘17’
- uses: android-actions/setup-android@v4
- uses: nttld/setup-ndk@v1
id: ndk
with:
ndk-version: r28b
- uses: dtolnay/rust-toolchain@stable
with:
toolchain: ‘1.91’
targets: aarch64-linux-android,armv7-linux-androideabi
- name: Set Android environment
shell: bash
run: |
echo “NDK_HOME=${{ steps.ndk.outputs.ndk-path }}” >> “$GITHUB_ENV”
echo “ANDROID_NDK_HOME=${{ steps.ndk.outputs.ndk-path }}” >> “$GITHUB_ENV”
- name: Install dependencies
run: pnpm install --frozen-lockfile
- name: Test native protocol
run: cargo test --manifest-path engine/Cargo.toml -p sendme-protocol -p sendme-native
- name: Build debug APK
run: pnpm tauri android build --debug
- uses: actions/upload-artifact@v4
with:
name: dashbeam-android
path: src-tauri/gen/android/app/build/outputs/apk/**/*.apk
if-no-files-found: error
‘’',
}

PROTOCOL_VARIANTS = r’‘’ /// Resolve a session-only alias over the existing encrypted control channel.
AliasLookupRequest {
alias: String,
lookup_nonce: u64,
},
AliasLookupResponse {
success: bool,
#[serde(default, skip_serializing_if = “Option::is_none”)]
blob_ticket: Option,
#[serde(default, skip_serializing_if = “Option::is_none”)]
error_code: Option,
lookup_nonce: u64,
},
‘’’

PROTOCOL_ERROR_ENUM = r’‘’
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = “snake_case”)]
pub enum AliasLookupErrorCode {
InvalidAlias,
NotFound,
Expired,
}
‘’’

PROTOCOL_TESTS = r’‘’
#[tokio::test]
async fn alias_messages_round_trip_and_echo_nonce() {
let (mut client, mut server) = tokio::io::duplex(4096);
let request = ControlMessage::AliasLookupRequest {
alias: “my-code”.to_string(),
lookup_nonce: 42,
};
write_message(&mut client, &request).await.unwrap();

match read_message(&mut server).await.unwrap() { ControlMessage::AliasLookupRequest { alias, lookup_nonce, } => { assert_eq!(alias, "my-code"); assert_eq!(lookup_nonce, 42); } other => panic!("expected alias request, got {other:?}"), } let (mut client, mut server) = tokio::io::duplex(4096); let response = ControlMessage::AliasLookupResponse { success: false, blob_ticket: None, error_code: Some(super::AliasLookupErrorCode::Expired), lookup_nonce: 42, }; write_message(&mut server, &response).await.unwrap(); match read_message(&mut client).await.unwrap() { ControlMessage::AliasLookupResponse { success, error_code, lookup_nonce, .. } => { assert!(!success); assert_eq!(error_code, Some(super::AliasLookupErrorCode::Expired)); assert_eq!(lookup_nonce, 42); } other => panic!("expected alias response, got {other:?}"), } } #[test] fn alias_message_kind_matches_wire_tag() { let messages = [ ControlMessage::AliasLookupRequest { alias: "test-code".to_string(), lookup_nonce: 7, }, ControlMessage::AliasLookupResponse { success: false, blob_ticket: None, error_code: Some(super::AliasLookupErrorCode::NotFound), lookup_nonce: 7, }, ]; for message in messages { let value = serde_json::to_value(&message).unwrap(); assert_eq!(value["type"].as_str(), Some(message.kind())); } } 

‘’’

NODE_ALIAS_HANDLER = r’‘’ let msg = match msg {
ControlMessage::AliasLookupRequest {
alias,
lookup_nonce,
} => {
let result = self.ctx.lan_alias_registry.lock().await.resolve(&alias);
let response = match result {
Ok(blob_ticket) => ControlMessage::AliasLookupResponse {
success: true,
blob_ticket: Some(blob_ticket),
error_code: None,
lookup_nonce,
},
Err(crate::lan_alias::AliasError::Invalid) => {
ControlMessage::AliasLookupResponse {
success: false,
blob_ticket: None,
error_code: Some(AliasLookupErrorCode::InvalidAlias),
lookup_nonce,
}
}
Err(crate::lan_alias::AliasError::Expired) => {
ControlMessage::AliasLookupResponse {
success: false,
blob_ticket: None,
error_code: Some(AliasLookupErrorCode::Expired),
lookup_nonce,
}
}
Err(_) => ControlMessage::AliasLookupResponse {
success: false,
blob_ticket: None,
error_code: Some(AliasLookupErrorCode::NotFound),
lookup_nonce,
},
};

if let Err(error) = write_message(&mut send, &response).await { tracing::debug!( target: "dashbeam::_events::control::alias_reply_failed", remote = %remote.fmt_short(), %error, ); } continue; } ControlMessage::AliasLookupResponse { .. } => { // Responses are consumed by the client-side lookup stream. continue; } other => other, }; 

‘’’

NODE_METHODS = r’‘’
pub async fn register_lan_alias(
&self,
alias: &str,
blob_ticket: &str,
) -> anyhow::Result<()> {
self.lan_alias_registry
.lock()
.await
.register(alias, blob_ticket)
.map_err(Into::into)
}

pub async fn clear_lan_alias(&self) { self.lan_alias_registry.lock().await.clear(); } pub async fn query_lan_alias( &self, remote_endpoint_id: &str, alias: &str, lookup_nonce: u64, ) -> anyhow::Result<Option<String>> { use iroh_blobs::ticket::BlobTicket; const LOOKUP_TIMEOUT: Duration = Duration::from_secs(5); let normalized = LanAliasRegistry::normalize_alias(alias)?; let nearby = self .nearby .lock() .await .list() .into_iter() .any(|device| { device.identified && device .endpoint_id .eq_ignore_ascii_case(remote_endpoint_id) }); anyhow::ensure!(nearby, "endpoint is not an identified Nearby candidate"); let remote = EndpointId::from_str(remote_endpoint_id) .context("invalid nearby endpoint id")?; let endpoint = { let runtime = self.runtime.lock().await; runtime.endpoint.clone() }; let addr = build_control_connect_addr(&endpoint, remote, None); let connection = tokio::time::timeout( LOOKUP_TIMEOUT, endpoint.connect(addr, CONTROL_ALPN), ) .await .context("alias lookup connection timed out")? .context("alias lookup connection failed")?; anyhow::ensure!( has_direct_path(&connection).await, "alias lookup requires a direct connection" ); let (mut send, mut recv) = tokio::time::timeout( LOOKUP_TIMEOUT, connection.open_bi(), ) .await .context("alias lookup stream timed out")? .context("failed to open alias lookup stream")?; tokio::time::timeout( LOOKUP_TIMEOUT, write_message( &mut send, &ControlMessage::AliasLookupRequest { alias: normalized, lookup_nonce, }, ), ) .await .context("alias lookup write timed out")? .context("failed to write alias lookup request")?; send.finish().context("failed to finish alias lookup request")?; let response = tokio::time::timeout( LOOKUP_TIMEOUT, read_message(&mut recv), ) .await .context("alias lookup response timed out")? .context("peer does not support LAN alias lookup")?; match response { ControlMessage::AliasLookupResponse { success, blob_ticket, lookup_nonce: response_nonce, .. } => { anyhow::ensure!( response_nonce == lookup_nonce, "alias lookup nonce mismatch" ); if !success { return Ok(None); } let ticket = blob_ticket .filter(|value| !value.trim().is_empty()) .context("peer returned an empty blob ticket")?; BlobTicket::from_str(&ticket) .context("peer returned a malformed blob ticket")?; Ok(Some(ticket)) } other => anyhow::bail!( "peer returned unexpected control message {}", other.kind() ), } } pub fn random_lookup_nonce() -> u64 { loop { let nonce = rand::random::<u64>(); if nonce != 0 { return nonce; } } } 

‘’’

TAURI_COMMANDS = r’‘’
// ALT_SENDME_LAN_ALIAS_V1
#[derive(Debug, serde::Serialize)]
#[serde(rename_all = “camelCase”)]
pub struct AliasPeerIdentity {
endpoint_id: String,
display_name: Option,
fingerprint: String,
}

#[derive(Debug, serde::Serialize)]
#[serde(tag = “status”, rename_all = “snake_case”)]
pub enum AliasResolutionOutcome {
NotFound,
UniqueMatch {
#[serde(rename = “blobTicket”)]
blob_ticket: String,
},
Ambiguous {
peers: Vec,
},
Error {
code: String,
message: String,
},
}

#[cfg(any(desktop, target_os = “android”))]
#[tauri::command]
pub async fn register_lan_alias(
alias: String,
state: State<'_, AppStateMutex>,
) -> Result<(), String> {
let normalized =
engine::LanAliasRegistry::normalize_alias(&alias).map_err(|error| error.to_string())?;

let (node, ticket) = { let app_state = state.lock().await; let node = app_state .node .clone() .ok_or_else(|| "Nearby is unavailable".to_string())?; let ticket = app_state .current_share .as_ref() .map(|share| share.ticket.clone()) .ok_or_else(|| "No active share".to_string())?; (node, ticket) }; node.register_lan_alias(&normalized, &ticket) .await .map_err(|error| error.to_string()) 

}

#[cfg(any(desktop, target_os = “android”))]
#[tauri::command]
pub async fn clear_lan_alias(
state: State<'_, AppStateMutex>,
) -> Result<(), String> {
let node = state
.lock()
.await
.node
.clone()
.ok_or_else(|| “Nearby is unavailable”.to_string())?;
node.clear_lan_alias().await;
Ok(())
}

#[cfg(any(desktop, target_os = “android”))]
#[tauri::command]
pub async fn resolve_lan_alias(
alias: String,
state: State<'_, AppStateMutex>,
) -> Result<AliasResolutionOutcome, String> {
use iroh_blobs::ticket::BlobTicket;
use std::str::FromStr;

let normalized = match engine::LanAliasRegistry::normalize_alias(&alias) { Ok(alias) => alias, Err(error) => { return Ok(AliasResolutionOutcome::Error { code: "invalid_alias".to_string(), message: error.to_string(), }); } }; let node = { let app_state = state.lock().await; match app_state.node.clone() { Some(node) => node, None => { return Ok(AliasResolutionOutcome::Error { code: "nearby_unavailable".to_string(), message: "Nearby is unavailable".to_string(), }); } } }; let peers: Vec<_> = node .list_nearby() .await .into_iter() .filter(|peer| peer.identified) .collect(); if peers.is_empty() { return Ok(AliasResolutionOutcome::Error { code: "nearby_unavailable".to_string(), message: "No identified Nearby devices are available".to_string(), }); } let lookup_nonce = engine::NodeService::random_lookup_nonce(); let concurrency = std::sync::Arc::new(tokio::sync::Semaphore::new(8)); let mut tasks = tokio::task::JoinSet::new(); for peer in peers.iter().cloned() { let node = node.clone(); let alias = normalized.clone(); let permit_pool = concurrency.clone(); tasks.spawn(async move { let permit = permit_pool.acquire_owned().await; if permit.is_err() { return (peer.endpoint_id, None); } let _permit = permit.expect("semaphore was checked"); let result = tokio::time::timeout( std::time::Duration::from_secs(6), node.query_lan_alias(&peer.endpoint_id, &alias, lookup_nonce), ) .await; let ticket = match result { Ok(Ok(Some(ticket))) if BlobTicket::from_str(&ticket).is_ok() => Some(ticket), Ok(Ok(_)) | Ok(Err(_)) | Err(_) => None, }; (peer.endpoint_id, ticket) }); } let mut matches = std::collections::BTreeMap::<String, String>::new(); while let Some(joined) = tasks.join_next().await { let Ok((endpoint_id, Some(ticket))) = joined else { continue; }; matches.entry(endpoint_id).or_insert(ticket); } match matches.len() { 0 => Ok(AliasResolutionOutcome::NotFound), 1 => Ok(AliasResolutionOutcome::UniqueMatch { blob_ticket: matches .into_values() .next() .expect("one alias match"), }), _ => { let peers = peers .into_iter() .filter(|peer| matches.contains_key(&peer.endpoint_id)) .map(|peer| AliasPeerIdentity { endpoint_id: peer.endpoint_id, display_name: peer.display_name, fingerprint: peer.fingerprint, }) .collect(); Ok(AliasResolutionOutcome::Ambiguous { peers }) } } 

}

#[cfg(not(any(desktop, target_os = “android”)))]
#[tauri::command]
pub async fn register_lan_alias(
_alias: String,
state: State<', AppStateMutex>,
) -> Result<(), String> {
Err(“LAN aliases are unavailable on this platform”.to_string())
}

#[cfg(not(any(desktop, target_os = “android”)))]
#[tauri::command]
pub async fn clear_lan_alias(
state: State<', AppStateMutex>,
) -> Result<(), String> {
Err(“LAN aliases are unavailable on this platform”.to_string())
}

#[cfg(not(any(desktop, target_os = “android”)))]
#[tauri::command]
pub async fn resolve_lan_alias(
_alias: String,
state: State<', AppStateMutex>,
) -> Result<AliasResolutionOutcome, String> {
Err(“LAN aliases are unavailable on this platform”.to_string())
}

‘’’

SENDER_ALIAS_UI = r’‘’



{t(‘common:sender.lanAlias.label’)}

<input
id=“lan-alias”
type=“text”
value={lanAlias}
onChange={(event) => setLanAlias(event.target.value)}
placeholder={t(‘common:sender.lanAlias.placeholder’)}
maxLength={32}
autoCapitalize=“none”
autoCorrect=“off”
className=“flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm”
/>


{t(‘common:sender.lanAlias.hint’)}


{aliasRegistrationError ? (


{aliasRegistrationError}


) : null}

‘’’

RECEIVER_HANDLE = r’‘’	const handleReceive = async () => {
const classified = classifyReceiveInput(ticket)

	if (classified.kind === 'invalid_alias') { 		showAlert( 			t('common:receiver.lanAlias.invalidTitle'), 			t('common:receiver.lanAlias.invalid'), 			'error' 		) 		return 	} 	if (classified.kind === 'raw_ticket') { 		await receiveWithTicket(classified.ticket) 		return 	} 	try { 		const outcome = await invoke<AliasResolutionOutcome>( 			'resolve_lan_alias', 			{ alias: classified.alias } 		) 		switch (outcome.status) { 			case 'unique_match': 				setTicket(outcome.blobTicket) 				await receiveWithTicket(outcome.blobTicket) 				return 			case 'not_found': 				showAlert( 					t('common:receiver.lanAlias.notFoundTitle'), 					t('common:receiver.lanAlias.notFound'), 					'error' 				) 				return 			case 'ambiguous': 				showAlert( 					t('common:receiver.lanAlias.ambiguousTitle'), 					t('common:receiver.lanAlias.ambiguous', { 						count: outcome.peers.length, 					}), 					'error' 				) 				return 			case 'error': 				showAlert( 					t('common:receiver.lanAlias.unavailableTitle'), 					outcome.message || 						t('common:receiver.lanAlias.unavailable'), 					'error' 				) 				return 		} 	} catch (error) { 		showAlert( 			t('common:receiver.lanAlias.timeoutTitle'), 			`${t('common:receiver.lanAlias.timeout')}: ${String(error)}`, 			'error' 		) 	} } 

‘’’

TRANSLATION_SENDER = r’‘’,
“lanAlias”: {
“label”: “LAN code (optional)”,
“placeholder”: “e.g. mycode123”,
“hint”: “4–32 ASCII letters, numbers, hyphens, or underscores. The share starts before this code is registered.”,
“active”: “LAN code: {{alias}}”,
“registrationFailed”: “The share is active, but the LAN code could not be registered: {{error}}”
}‘’’

TRANSLATION_RECEIVER = r’‘’,
“lanAlias”: {
“invalidTitle”: “Invalid LAN code”,
“invalid”: “Use 4–32 ASCII letters, numbers, hyphens, or underscores.”,
“notFoundTitle”: “LAN code not found”,
“notFound”: “No nearby sender currently has this code. The code may have expired.”,
“ambiguousTitle”: “Multiple nearby senders matched”,
“ambiguous”: “{{count}} nearby senders use this code. Ask the sender to choose a different code.”,
“unavailableTitle”: “Nearby unavailable”,
“unavailable”: “Nearby discovery is unavailable. Check that both devices are on the same Wi-Fi or hotspot.”,
“timeoutTitle”: “LAN lookup timed out”,
“timeout”: “No nearby sender answered in time.”
}‘’’

class ApplyError(RuntimeError):
pass

def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
return subprocess.run(
command,
text=True,
stdout=subprocess.PIPE,
stderr=subprocess.PIPE,
check=check,
)

def require_root(root: Path) -> None:
required = [
“.git”,
“engine/Cargo.toml”,
“engine/native/src/node.rs”,
“engine/protocol/src/control.rs”,
“src-tauri/Cargo.toml”,
“frontend/src/components/sender/Sender.tsx”,
“frontend/src/hooks/useReceiver.ts”,
“src-tauri/gen/android/app/src/main/AndroidManifest.xml”,
]
missing = [path for path in required if not (root / path).exists()]
if missing:
raise ApplyError(
"Run this script at the DashBeam repository root; missing: "
+ ", ".join(missing)
)

top = run(["git", "rev-parse", "--show-toplevel"]).stdout.strip() if Path(top).resolve() != root.resolve(): raise ApplyError("current directory is not the Git repository root") head = run(["git", "rev-parse", "HEAD"]).stdout.strip() if head != EXPECTED_HEAD: raise ApplyError( f"unsupported repository revision {head}; expected {EXPECTED_HEAD}" ) 

def check_clean_tree() -> None:
output = run([“git”, “status”, “–porcelain=v1”, “–untracked-files=all”]).stdout
unexpected: list[str] = []

for line in output.splitlines(): path_field = line[3:] if " -> " in path_field: path_field = path_field.split(" -> ", 1)[1] path_field = path_field.strip('"') if path_field not in ALLOWED_DIRTY_PATHS: unexpected.append(line) if unexpected: raise ApplyError( "Git working tree is not clean. Only apply_altsendme.py and " "altsendme.patch may be untracked:\n" + "\n".join(unexpected) ) 

def read_required(root: Path, relative: str) -> str:
path = root / relative
if not path.is_file():
raise ApplyError(f"required file is missing: {relative}")
return path.read_text(encoding=“utf-8”)

def replace_once(text: str, old: str, new: str, label: str) -> str:
count = text.count(old)
if count != 1:
raise ApplyError(f"{label}: expected anchor exactly once, found {count}")
return text.replace(old, new, 1)

def replace_count(text: str, old: str, new: str, expected: int, label: str) -> str:
count = text.count(old)
if count != expected:
raise ApplyError(f"{label}: expected anchor {expected} times, found {count}")
return text.replace(old, new)

def stage_changes(root: Path) -> dict[str, str]:
staged: dict[str, str] = {}

for relative, content in NEW_FILES.items(): path = root / relative if path.exists(): raise ApplyError(f"new target already exists unexpectedly: {relative}") staged[relative] = content native_lib = read_required(root, "engine/native/src/lib.rs") native_lib = replace_once( native_lib, "pub mod lan_discovery;\n", "pub mod lan_alias;\npub mod lan_discovery;\n", "native lib module", ) native_lib = replace_once( native_lib, "pub use nearby::{NearbyDevice, NearbyRegistry, ObserveOutcome};\n", "pub use lan_alias::{AliasError, LanAliasRegistry};\n" "pub use nearby::{NearbyDevice, NearbyRegistry, ObserveOutcome};\n", "native lib export", ) staged["engine/native/src/lib.rs"] = native_lib protocol_lib = read_required(root, "engine/protocol/src/lib.rs") protocol_lib = replace_once( protocol_lib, "pub use control::{ControlMessage, PairingTicket, CONTROL_ALPN, RememberVote, InviteResponse};", "pub use control::{\n" " AliasLookupErrorCode, ControlMessage, InviteResponse, PairingTicket, RememberVote,\n" " CONTROL_ALPN,\n" "};", "protocol exports", ) staged["engine/protocol/src/lib.rs"] = protocol_lib control = read_required(root, "engine/protocol/src/control.rs") control = replace_once( control, " PairRequest {\n" " sender_name: String,\n" " device_type: String,\n" " #[serde(default)]\n" " os: String,\n" " },\n", " PairRequest {\n" " sender_name: String,\n" " device_type: String,\n" " #[serde(default)]\n" " os: String,\n" " },\n" + PROTOCOL_VARIANTS, "control variants", ) control = replace_once( control, ' Self::PairRequest { .. } => "pair-request",\n', ' Self::PairRequest { .. } => "pair-request",\n' ' Self::AliasLookupRequest { .. } => "alias-lookup-request",\n' ' Self::AliasLookupResponse { .. } => "alias-lookup-response",\n', "control kinds", ) control = replace_once( control, "\n#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]\n" '#[serde(rename_all = "lowercase")]\n' "pub enum RememberVote", PROTOCOL_ERROR_ENUM + "\n#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]\n" '#[serde(rename_all = "lowercase")]\n' "pub enum RememberVote", "control error enum", ) control = replace_once( control, " ControlMessage::PairRequest {\n" " sender_name: String::new(),\n" " device_type: String::new(),\n" " os: String::new(),\n" " },\n" " ];", " ControlMessage::PairRequest {\n" " sender_name: String::new(),\n" " device_type: String::new(),\n" " os: String::new(),\n" " },\n" " ControlMessage::AliasLookupRequest {\n" " alias: String::new(),\n" " lookup_nonce: 1,\n" " },\n" " ControlMessage::AliasLookupResponse {\n" " success: false,\n" " blob_ticket: None,\n" " error_code: Some(super::AliasLookupErrorCode::NotFound),\n" " lookup_nonce: 1,\n" " },\n" " ];", "control kind samples", ) control = replace_once( control, "\n #[test]\n fn identity_os_defaults_when_absent()", PROTOCOL_TESTS + "\n #[test]\n fn identity_os_defaults_when_absent()", "control alias tests", ) staged["engine/protocol/src/control.rs"] = control nearby = read_required(root, "engine/protocol/src/nearby.rs") nearby = replace_once( nearby, " | ControlMessage::PairRequest { .. }\n", " | ControlMessage::PairRequest { .. }\n" " | ControlMessage::AliasLookupRequest { .. }\n", "unpaired alias policy", ) nearby = replace_once( nearby, " assert!(unpaired_message_allowed(&ControlMessage::PairRequest {\n" ' sender_name: "Alice".to_string(),\n' ' device_type: "laptop".to_string(),\n' ' os: "macos".to_string(),\n' " }));\n", " assert!(unpaired_message_allowed(&ControlMessage::PairRequest {\n" ' sender_name: "Alice".to_string(),\n' ' device_type: "laptop".to_string(),\n' ' os: "macos".to_string(),\n' " }));\n" " assert!(unpaired_message_allowed(\n" " &ControlMessage::AliasLookupRequest {\n" ' alias: "test-code".to_string(),\n' " lookup_nonce: 42,\n" " }\n" " ));\n" " assert!(!unpaired_message_allowed(\n" " &ControlMessage::AliasLookupResponse {\n" " success: false,\n" " blob_ticket: None,\n" " error_code: Some(crate::control::AliasLookupErrorCode::NotFound),\n" " lookup_nonce: 42,\n" " }\n" " ));\n", "unpaired alias tests", ) staged["engine/protocol/src/nearby.rs"] = nearby engine_lib = read_required(root, "engine/src/lib.rs") engine_lib = replace_once( engine_lib, " sign_challenge, unpaired_message_allowed, verify_challenge, verify_relays, ControlMessage,\n", " sign_challenge, unpaired_message_allowed, verify_challenge, verify_relays,\n" " AliasLookupErrorCode, ControlMessage,\n", "engine protocol re-export", ) staged["engine/src/lib.rs"] = engine_lib node = read_required(root, "engine/native/src/node.rs") node = replace_once( node, " DiscoveryModeOption, InviteResponse, PairedDevice, PairingStatus, RememberVote,\n", " AliasLookupErrorCode, DiscoveryModeOption, InviteResponse, PairedDevice, PairingStatus,\n" " RememberVote,\n", "node protocol import", ) node = replace_once( node, "use crate::lan_discovery::{LanDiscovery, LanEvent};\n", "use crate::lan_alias::LanAliasRegistry;\n" "use crate::lan_discovery::{LanDiscovery, LanEvent};\n", "node alias import", ) node = replace_once( node, " unpaired_limiter: Arc<std::sync::Mutex<UnpairedRateLimiter>>,\n" "}", " unpaired_limiter: Arc<std::sync::Mutex<UnpairedRateLimiter>>,\n" " lan_alias_registry: Arc<Mutex<LanAliasRegistry>>,\n" "}", "control context registry", ) node = replace_once( node, " if let ControlMessage::WhoAreYou = msg {\n", NODE_ALIAS_HANDLER + " if let ControlMessage::WhoAreYou = msg {\n", "control alias handler", ) node = replace_once( node, " ControlMessage::WhoAreYou\n" " | ControlMessage::Identity { .. }\n" " | ControlMessage::PairRequest { .. } => {\n", " ControlMessage::WhoAreYou\n" " | ControlMessage::Identity { .. }\n" " | ControlMessage::PairRequest { .. }\n" " | ControlMessage::AliasLookupRequest { .. }\n" " | ControlMessage::AliasLookupResponse { .. } => {\n", "pairing-host exhaustive match", ) node = replace_once( node, " nearby_unavailable: Arc<std::sync::RwLock<Option<String>>>,\n", " nearby_unavailable: Arc<std::sync::RwLock<Option<String>>>,\n" " lan_alias_registry: Arc<Mutex<LanAliasRegistry>>,\n", "node service registry field", ) node = replace_once( node, " let unpaired_limiter = Arc::new(std::sync::Mutex::new(UnpairedRateLimiter::new()));\n", " let unpaired_limiter = Arc::new(std::sync::Mutex::new(UnpairedRateLimiter::new()));\n" " let lan_alias_registry = Arc::new(Mutex::new(LanAliasRegistry::new()));\n", "registry construction", ) node = replace_count( node, " presence.clone(),\n" " paired_connections.clone(),\n", " presence.clone(),\n" " lan_alias_registry.clone(),\n" " paired_connections.clone(),\n", 2, "build_runtime call registry arguments", ) node = replace_once( node, " nearby_unavailable,\n" " unpaired_limiter,\n", " nearby_unavailable,\n" " lan_alias_registry,\n" " unpaired_limiter,\n", "node initializer registry", ) node = replace_once( node, " /// Sends an already-minted share ticket to a nearby device", NODE_METHODS + " /// Sends an already-minted share ticket to a nearby device", "node public alias methods", ) node = replace_once( node, " presence: Arc<std::sync::RwLock<HashMap<String, bool>>>,\n" " paired_connections: Arc<PairedConnectionManager>,\n", " presence: Arc<std::sync::RwLock<HashMap<String, bool>>>,\n" " lan_alias_registry: Arc<Mutex<LanAliasRegistry>>,\n" " paired_connections: Arc<PairedConnectionManager>,\n", "build_runtime signature registry", ) node = replace_once( node, " unpaired_limiter: unpaired_limiter.clone(),\n" " };", " unpaired_limiter: unpaired_limiter.clone(),\n" " lan_alias_registry,\n" " };", "control context initializer registry", ) staged["engine/native/src/node.rs"] = node commands = read_required(root, "src-tauri/src/commands.rs") commands = replace_once( commands, "/// Stop the current sharing session\n", TAURI_COMMANDS + "/// Stop the current sharing session\n", "Tauri alias commands", ) commands = replace_once( commands, " let start_result = async {\n", " #[cfg(any(desktop, target_os = \"android\"))]\n" " if let Some(node) = state.lock().await.node.clone() {\n" " node.clear_lan_alias().await;\n" " }\n\n" " let start_result = async {\n", "clear before new share", ) commands = replace_once( commands, " #[cfg(any(desktop, target_os = \"android\"))]\n" " if let Some(node) = app_state.node.as_ref() {\n" " node.stop_pairing_host().await;\n" " }\n", " #[cfg(any(desktop, target_os = \"android\"))]\n" " if let Some(node) = app_state.node.as_ref() {\n" " node.clear_lan_alias().await;\n" " node.stop_pairing_host().await;\n" " }\n", "clear alias on stop", ) staged["src-tauri/src/commands.rs"] = commands tauri_lib = read_required(root, "src-tauri/src/lib.rs") tauri_lib = replace_once( tauri_lib, " send_items,\n" " stop_sharing,\n", " send_items,\n" " register_lan_alias,\n" " clear_lan_alias,\n" " resolve_lan_alias,\n" " stop_sharing,\n", "invoke handler aliases", ) staged["src-tauri/src/lib.rs"] = tauri_lib sender_hook = read_required(root, "frontend/src/hooks/useSender.ts") sender_hook = replace_once( sender_hook, "import { incrementPairedSendCount } from '@/lib/paired-send-counts'\n", "import { incrementPairedSendCount } from '@/lib/paired-send-counts'\n" "import { normalizeLanAlias } from '@/lib/lan-alias'\n", "sender alias import", ) sender_hook = replace_once( sender_hook, "\tpairedInviteStatus: Record<string, PairedInviteStatus>\n", "\tpairedInviteStatus: Record<string, PairedInviteStatus>\n" "\tregisteredLanAlias: string | null\n" "\taliasRegistrationError: string | null\n", "sender return alias state", ) sender_hook = replace_once( sender_hook, "\tstartSharing: () => Promise<void>\n", "\tstartSharing: (lanAlias?: string) => Promise<void>\n", "sender start signature", ) sender_hook = replace_once( sender_hook, "\tconst { isNodeReady, isNodeStatusPending } = useNodeCapability()\n", "\tconst { isNodeReady, isNodeStatusPending } = useNodeCapability()\n" "\tconst [registeredLanAlias, setRegisteredLanAlias] = useState<string | null>(null)\n" "\tconst [aliasRegistrationError, setAliasRegistrationError] = useState<string | null>(null)\n", "sender alias state", ) sender_hook = replace_once( sender_hook, "\tconst startSharing = async () => {\n", "\tconst startSharing = async (lanAlias?: string) => {\n" "\t\tconst requestedAlias = lanAlias?.trim() ?? ''\n" "\t\tconst normalizedAlias = requestedAlias\n" "\t\t\t? normalizeLanAlias(requestedAlias)\n" "\t\t\t: null\n" "\t\tsetAliasRegistrationError(null)\n" "\t\tsetRegisteredLanAlias(null)\n" "\t\tif (requestedAlias && !normalizedAlias) {\n" "\t\t\tsetAliasRegistrationError(\n" "\t\t\t\tt('common:receiver.lanAlias.invalid')\n" "\t\t\t)\n" "\t\t\treturn\n" "\t\t}\n", "sender start alias validation", ) sender_hook = replace_once( sender_hook, "\t\t\tsetTicket(result)\n" "\t\t\tsetViewState('SHARING')\n", "\t\t\tsetTicket(result)\n" "\t\t\tsetViewState('SHARING')\n" "\t\t\tif (normalizedAlias) {\n" "\t\t\t\ttry {\n" "\t\t\t\t\tawait invoke<void>('register_lan_alias', {\n" "\t\t\t\t\t\talias: normalizedAlias,\n" "\t\t\t\t\t})\n" "\t\t\t\t\tsetRegisteredLanAlias(normalizedAlias)\n" "\t\t\t\t} catch (error) {\n" "\t\t\t\t\tsetAliasRegistrationError(\n" "\t\t\t\t\t\tt('common:sender.lanAlias.registrationFailed', {\n" "\t\t\t\t\t\t\terror: String(error),\n" "\t\t\t\t\t\t})\n" "\t\t\t\t\t)\n" "\t\t\t\t}\n" "\t\t\t}\n", "sender register after share", ) sender_hook = replace_once( sender_hook, "\t\tpairedInviteStatus,\n" "\t\tonInvitePairedDevice,\n", "\t\tpairedInviteStatus,\n" "\t\tregisteredLanAlias,\n" "\t\taliasRegistrationError,\n" "\t\tonInvitePairedDevice,\n", "sender return alias values", ) staged["frontend/src/hooks/useSender.ts"] = sender_hook sender = read_required(root, "frontend/src/components/sender/Sender.tsx") sender = replace_once( sender, "import { useEffect } from 'react'\n", "import { useEffect, useState } from 'react'\n", "sender state import", ) sender = replace_once( sender, "export function Sender({ onTransferStateChange }: SenderProps) {\n", "export function Sender({ onTransferStateChange }: SenderProps) {\n" "\tconst [lanAlias, setLanAlias] = useState('')\n", "sender alias input state", ) sender = replace_once( sender, "\t\tpairedInviteStatus,\n", "\t\tpairedInviteStatus,\n" "\t\tregisteredLanAlias,\n" "\t\taliasRegistrationError,\n", "sender hook fields", ) sender = replace_once( sender, "\t\t\t\t\t\t<ShareActionCard\n", SENDER_ALIAS_UI + "\t\t\t\t\t\t<ShareActionCard\n", "sender alias field", ) sender = replace_once( sender, "\t\t\t\t\t\t\tonStartSharing={startSharing}\n", "\t\t\t\t\t\t\tonStartSharing={() => startSharing(lanAlias)}\n", "sender start callback", ) sender = replace_once( sender, "\t\t\t\t\t<SharingActiveCard\n", "\t\t\t\t\t{registeredLanAlias ? (\n" "\t\t\t\t\t\t<p className=\"mb-3 text-center text-sm text-muted-foreground\">\n" "\t\t\t\t\t\t\t{t('common:sender.lanAlias.active', {\n" "\t\t\t\t\t\t\t\talias: registeredLanAlias,\n" "\t\t\t\t\t\t\t})}\n" "\t\t\t\t\t\t</p>\n" "\t\t\t\t\t) : null}\n" "\t\t\t\t\t{aliasRegistrationError ? (\n" "\t\t\t\t\t\t<p role=\"alert\" className=\"mb-3 text-sm text-destructive\">\n" "\t\t\t\t\t\t\t{aliasRegistrationError}\n" "\t\t\t\t\t\t</p>\n" "\t\t\t\t\t) : null}\n" "\t\t\t\t\t<SharingActiveCard\n", "sender active alias status", ) staged["frontend/src/components/sender/Sender.tsx"] = sender receiver_hook = read_required(root, "frontend/src/hooks/useReceiver.ts") receiver_hook = replace_once( receiver_hook, "import { ticketFromReceiveLink } from '../lib/receive-link'\n", "import { ticketFromReceiveLink } from '../lib/receive-link'\n" "import {\n" "\tclassifyReceiveInput,\n" "\ttype AliasResolutionOutcome,\n" "} from '../lib/lan-alias'\n", "receiver alias import", ) receiver_hook = replace_once( receiver_hook, "\t\tconst trimmed = ticket.trim()\n" "\t\tif (!trimmed) {\n", "\t\tconst trimmed = ticket.trim()\n" "\t\tif (!trimmed) {\n", "receiver preview initial anchor", ) receiver_hook = replace_once( receiver_hook, "\t\tsetIsPreviewLoading(true)\n" "\t\t// Clear stale preview while typing/fetching\n", "\t\tif (classifyReceiveInput(trimmed).kind !== 'raw_ticket') {\n" "\t\t\tsetPreviewMetadata(null)\n" "\t\t\tpreviewMetadataRef.current = null\n" "\t\t\tsetIsPreviewLoading(false)\n" "\t\t\treturn\n" "\t\t}\n\n" "\t\tsetIsPreviewLoading(true)\n" "\t\t// Clear stale preview while typing/fetching\n", "receiver skip alias preview", ) receiver_hook = replace_once( receiver_hook, "\tconst handleReceive = async () => {\n" "\t\tawait receiveWithTicket(ticket)\n" "\t}\n", RECEIVER_HANDLE, "receiver alias resolution", ) staged["frontend/src/hooks/useReceiver.ts"] = receiver_hook platform_api = read_required(root, "frontend/src/lib/platform-api.ts") platform_api = replace_once( platform_api, "\t\tcase 'get_pairing_ticket':\n" "\t\t\treturn null as T\n", "\t\tcase 'get_pairing_ticket':\n" "\t\t\treturn null as T\n" "\t\tcase 'resolve_lan_alias':\n" "\t\t\treturn {\n" "\t\t\t\tstatus: 'error',\n" "\t\t\t\tcode: 'nearby_unavailable',\n" "\t\t\t\tmessage: 'LAN aliases are unavailable in the browser',\n" "\t\t\t} as T\n" "\t\tcase 'register_lan_alias':\n" "\t\tcase 'clear_lan_alias':\n" "\t\t\tthrow new WebPreviewError('LAN aliases are unavailable in the browser')\n", "web alias stubs", ) staged["frontend/src/lib/platform-api.ts"] = platform_api locale = read_required(root, "frontend/src/locales/en/common.json") locale = replace_once( locale, '\t\t"sharingActive": {', '\t\t"sharingActive": {', "sender translation location check", ) locale = replace_once( locale, '\t\t"pairedDevices": {', '\t\t"pairedDevices": {', "sender translation anchor check", ) sender_end_anchor = ( '\t\t\t}\n' '\t\t}\n' '\t},\n' '\t"receiver": {' ) locale = replace_once( locale, sender_end_anchor, '\t\t\t}\n' '\t\t}' + TRANSLATION_SENDER + '\n' '\t},\n' '\t"receiver": {', "sender translations", ) receiver_end_anchor = ( '\t\t"download": "Download"\n' '\t},\n' '\t"transfer": {' ) locale = replace_once( locale, receiver_end_anchor, '\t\t"download": "Download"' + TRANSLATION_RECEIVER + '\n' '\t},\n' '\t"transfer": {', "receiver translations", ) staged["frontend/src/locales/en/common.json"] = locale manifest = read_required( root, "src-tauri/gen/android/app/src/main/AndroidManifest.xml" ) manifest = replace_once( manifest, ' <uses-permission android:name="android.permission.INTERNET" />\n', ' <uses-permission android:name="android.permission.INTERNET" />\n' ' <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n' ' <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />\n' ' <uses-permission android:name="android.permission.CHANGE_WIFI_MULTICAST_STATE" />\n', "Android LAN permissions", ) staged["src-tauri/gen/android/app/src/main/AndroidManifest.xml"] = manifest kotlin_path = ( "src-tauri/plugins/tauri-plugin-native-utils/android/src/main/java/" "com/dashbeam/plugin/native_utils/NativeUtils.kt" ) kotlin = read_required(root, kotlin_path) kotlin = replace_once( kotlin, "import android.net.Uri\n", "import android.net.Uri\n" "import android.net.wifi.WifiManager\n" "import android.content.Context\n", "Kotlin multicast imports", ) kotlin = replace_once( kotlin, " private val pendingShareBatches = ConcurrentLinkedQueue<List<Uri>>()\n", " private val pendingShareBatches = ConcurrentLinkedQueue<List<Uri>>()\n" " private var multicastLock: WifiManager.MulticastLock? = null\n", "Kotlin multicast field", ) kotlin = replace_once( kotlin, " @Command\n" " fun start_presence_service(invoke: Invoke) {\n", " @Synchronized\n" " @Command\n" " fun acquire_multicast_lock(invoke: Invoke) {\n" " try {\n" " if (multicastLock?.isHeld != true) {\n" " val wifi = activity.applicationContext.getSystemService(\n" " Context.WIFI_SERVICE\n" " ) as WifiManager\n" " multicastLock = wifi.createMulticastLock(\n" ' "dashbeam-mdns"\n' " ).apply {\n" " setReferenceCounted(true)\n" " acquire()\n" " }\n" " }\n" " invoke.resolve()\n" " } catch (error: Exception) {\n" " invoke.reject(error.message ?: \"Failed to acquire multicast lock\")\n" " }\n" " }\n\n" " @Synchronized\n" " @Command\n" " fun release_multicast_lock(invoke: Invoke) {\n" " try {\n" " multicastLock?.let { lock ->\n" " if (lock.isHeld) lock.release()\n" " }\n" " multicastLock = null\n" " invoke.resolve()\n" " } catch (error: Exception) {\n" " invoke.reject(error.message ?: \"Failed to release multicast lock\")\n" " }\n" " }\n\n" " @Command\n" " fun start_presence_service(invoke: Invoke) {\n", "Kotlin multicast commands", ) kotlin = replace_once( kotlin, " scope.cancel()\n" " super.onDestroy()\n", " multicastLock?.let { lock ->\n" " if (lock.isHeld) lock.release()\n" " }\n" " multicastLock = null\n" " scope.cancel()\n" " super.onDestroy()\n", "Kotlin multicast cleanup", ) staged[kotlin_path] = kotlin plugin_mobile = read_required( root, "src-tauri/plugins/tauri-plugin-native-utils/src/mobile.rs" ) plugin_mobile = replace_once( plugin_mobile, "impl<R: Runtime> NativeUtils<R> {\n" " pub fn start_presence_service(&self) -> crate::Result<()> {\n", "impl<R: Runtime> NativeUtils<R> {\n" " pub fn acquire_multicast_lock(&self) -> crate::Result<()> {\n" " self.0\n" ' .run_mobile_plugin("acquire_multicast_lock", ())\n' " .map_err(Into::into)\n" " }\n\n" " pub fn release_multicast_lock(&self) -> crate::Result<()> {\n" " self.0\n" ' .run_mobile_plugin("release_multicast_lock", ())\n' " .map_err(Into::into)\n" " }\n" "}\n\n" "impl<R: Runtime> NativeUtils<R> {\n" " pub fn start_presence_service(&self) -> crate::Result<()> {\n", "Rust mobile multicast bindings", ) staged["src-tauri/plugins/tauri-plugin-native-utils/src/mobile.rs"] = plugin_mobile plugin_commands = read_required( root, "src-tauri/plugins/tauri-plugin-native-utils/src/commands.rs" ) plugin_commands = replace_once( plugin_commands, "#[command]\n" "pub(crate) async fn start_presence_service<R: Runtime>", "#[command]\n" "pub(crate) async fn acquire_multicast_lock<R: Runtime>(\n" " app: AppHandle<R>,\n" ") -> Result<()> {\n" " app.native_utils().acquire_multicast_lock()\n" "}\n\n" "#[command]\n" "pub(crate) async fn release_multicast_lock<R: Runtime>(\n" " app: AppHandle<R>,\n" ") -> Result<()> {\n" " app.native_utils().release_multicast_lock()\n" "}\n\n" "#[command]\n" "pub(crate) async fn start_presence_service<R: Runtime>", "plugin multicast commands", ) staged[ "src-tauri/plugins/tauri-plugin-native-utils/src/commands.rs" ] = plugin_commands plugin_lib = read_required( root, "src-tauri/plugins/tauri-plugin-native-utils/src/lib.rs" ) plugin_lib = replace_once( plugin_lib, " commands::start_presence_service,\n", " commands::acquire_multicast_lock,\n" " commands::release_multicast_lock,\n" " commands::start_presence_service,\n", "plugin invoke handlers", ) staged["src-tauri/plugins/tauri-plugin-native-utils/src/lib.rs"] = plugin_lib permissions = read_required( root, "src-tauri/plugins/tauri-plugin-native-utils/permissions/default.toml" ) permissions = replace_once( permissions, ' "allow-start-presence-service",\n', ' "allow-acquire-multicast-lock",\n' ' "allow-release-multicast-lock",\n' ' "allow-start-presence-service",\n', "plugin multicast permissions", ) staged[ "src-tauri/plugins/tauri-plugin-native-utils/permissions/default.toml" ] = permissions build_rs = read_required( root, "src-tauri/plugins/tauri-plugin-native-utils/build.rs" ) build_rs = replace_once( build_rs, ' "start_presence_service",\n', ' "acquire_multicast_lock",\n' ' "release_multicast_lock",\n' ' "start_presence_service",\n', "plugin permission generation", ) staged["src-tauri/plugins/tauri-plugin-native-utils/build.rs"] = build_rs return staged 

def validate_staged(staged: dict[str, str]) -> None:
required_markers = {
“engine/native/src/lan_alias.rs”: MARKER,
“frontend/src/lib/lan-alias.ts”: MARKER,
“src-tauri/src/commands.rs”: MARKER,
}
for path, marker in required_markers.items():
if marker not in staged[path]:
raise ApplyError(f"staged marker missing from {path}")

protocol = staged["engine/protocol/src/control.rs"] for token in [ "AliasLookupRequest", "AliasLookupResponse", "AliasLookupErrorCode", "lookup_nonce", ]: if token not in protocol: raise ApplyError(f"protocol validation failed: missing {token}") node = staged["engine/native/src/node.rs"] forbidden = "resolve_lan_alias_internal" if forbidden in node: raise ApplyError(f"forbidden local-registry query remains: {forbidden}") for token in [ "query_lan_alias", "send.finish()", "BlobTicket::from_str", "alias lookup nonce mismatch", "lan_alias_registry", ]: if token not in node: raise ApplyError(f"node validation failed: missing {token}") receiver = staged["frontend/src/hooks/useReceiver.ts"] if "lookupNonce" in receiver or "lookup_nonce" in receiver: raise ApplyError("frontend must not expose a lookup nonce") if "receiveWithTicket(outcome.blobTicket)" not in receiver: raise ApplyError("receiver does not feed the resolved ticket into receiveWithTicket") manifest = staged[ "src-tauri/gen/android/app/src/main/AndroidManifest.xml" ] for permission in [ "android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE", "android.permission.ACCESS_WIFI_STATE", "android.permission.CHANGE_WIFI_MULTICAST_STATE", ]: if permission not in manifest: raise ApplyError(f"Android permission missing: {permission}") workflow = staged[".github/workflows/altsendme-platform-build.yml"] if "release" in workflow.lower() and "upload-release-asset" in workflow.lower(): raise ApplyError("artifact workflow must not publish a GitHub Release") 

def atomic_write(path: Path, content: str) -> None:
path.parent.mkdir(parents=True, exist_ok=True)
fd, temporary = tempfile.mkstemp(
prefix=f".{path.name}.“,
suffix=”.tmp",
dir=str(path.parent),
)
temporary_path = Path(temporary)
try:
with os.fdopen(fd, “w”, encoding=“utf-8”, newline=“”) as handle:
handle.write(content)
handle.flush()
os.fsync(handle.fileno())
os.replace(temporary_path, path)
finally:
if temporary_path.exists():
temporary_path.unlink()

def main() -> int:
root = Path.cwd()

try: require_root(root) already = root / "engine/native/src/lan_alias.rs" if already.exists() and MARKER in already.read_text(encoding="utf-8"): print("AltSendme LAN alias implementation is already applied.") return 0 check_clean_tree() staged = stage_changes(root) validate_staged(staged) timestamp = _datetime.datetime.now().strftime("%Y%m%d-%H%M%S") backup_root = root / ".altsendme-backups" / timestamp originals: dict[str, bytes | None] = {} for relative in sorted(staged): path = root / relative originals[relative] = path.read_bytes() if path.exists() else None backup_root.mkdir(parents=True, exist_ok=False) for relative, original in originals.items(): if original is None: continue backup = backup_root / relative backup.parent.mkdir(parents=True, exist_ok=True) backup.write_bytes(original) changed: list[str] = [] try: for relative in sorted(staged): atomic_write(root / relative, staged[relative]) changed.append(relative) for relative, expected in staged.items(): actual = (root / relative).read_text(encoding="utf-8") if actual != expected: raise ApplyError(f"post-write content mismatch: {relative}") validate_staged( { relative: (root / relative).read_text(encoding="utf-8") for relative in staged } ) except BaseException: restore_errors: list[str] = [] for relative in reversed(changed): path = root / relative original = originals[relative] try: if original is None: if path.exists(): path.unlink() else: path.parent.mkdir(parents=True, exist_ok=True) fd, temporary = tempfile.mkstemp( prefix=f".{path.name}.restore.", suffix=".tmp", dir=str(path.parent), ) temporary_path = Path(temporary) try: with os.fdopen(fd, "wb") as handle: handle.write(original) handle.flush() os.fsync(handle.fileno()) os.replace(temporary_path, path) finally: if temporary_path.exists(): temporary_path.unlink() except Exception as error: restore_errors.append(f"{relative}: {error}") if restore_errors: print( "WARNING: restoration errors:\n" + "\n".join(restore_errors), file=sys.stderr, ) raise print(f"Backups: {backup_root.relative_to(root)}") print("Changed files:") for relative in sorted(changed): print(f" {relative}") print() print("Validation commands:") commands = [ "cargo fmt --manifest-path engine/Cargo.toml -- --check", "cargo check --manifest-path engine/Cargo.toml", "cargo test --manifest-path engine/Cargo.toml -p sendme-protocol -p sendme-native", "pnpm install --frozen-lockfile", "pnpm run format:check", "pnpm run lint", "pnpm run test:lib", "pnpm run build", "cargo check --manifest-path src-tauri/Cargo.toml", "pnpm tauri build", "pnpm tauri android build --debug", ] for command in commands: print(f" {command}") print( " Windows: run the altsendme-platform-build workflow on a " "windows-latest GitHub Actions runner, or follow RELEASE.md." ) print() print("No commit or push was performed.") return 0 except ApplyError as error: print(f"apply_altsendme.py: {error}", file=sys.stderr) return 1 except subprocess.CalledProcessError as error: detail = error.stderr.strip() or error.stdout.strip() or str(error) print(f"apply_altsendme.py: command failed: {detail}", file=sys.stderr) return 1 except Exception as error: print(f"apply_altsendme.py: unexpected failure: {error}", file=sys.stderr) return 1 

if name == “main”:
raise SystemExit(main())

