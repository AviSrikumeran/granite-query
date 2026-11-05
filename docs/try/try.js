/* A visitor interface to the reviewed same-origin gateway, never to Modal.
   Loading this page only checks metadata. Paid work requires explicit submit.
   An uncertain request is kept in session storage and is never replayed. */
const SERVICE = 'granite-query-inference-gateway';
const MODEL = 'ibm-granite/granite-4.2-3b';
const REVISION = '4e9c275e232f10211ec88644d106a1f6a1b60e06';
const ATTEMPT_KEY = 'granite-query.try.last-attempt.v1';
const OUTPUT_CAP = 128;
const IS_RESEARCH_MIRROR = globalThis.location?.hostname === 'avisrikumeran.github.io';
const UUID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const $ = id => document.getElementById(id);
let metadata = null, checking = false, pending = false, unknown = null;
let localReservations = 0, expiryTimer = null, storageUsable = true;

function saveAttempt(attempt) {
  try {
    sessionStorage.setItem(ATTEMPT_KEY, JSON.stringify(attempt));
    storageUsable = true;
    return true;
  } catch {
    storageUsable = false;
    return false;
  }
}
try {
  const raw = sessionStorage.getItem(ATTEMPT_KEY);
  if (raw !== null) {
    const saved = JSON.parse(raw);
    if (!saved || !UUID.test(saved.request_id) || !Number.isFinite(Date.parse(saved.started_at)) || !['unknown', 'completed', 'not_started'].includes(saved.completion)) throw new Error('Invalid saved receipt');
    $('request-id').textContent = saved.request_id;
    if (saved.completion === 'unknown' && saved.acknowledged !== true) unknown = saved;
  }
  // Verify that an attempt can be saved before offering a paid submission.
  const key = ATTEMPT_KEY + '.check';
  sessionStorage.setItem(key, '1'); sessionStorage.removeItem(key);
} catch {
  storageUsable = false;
}

function remaining() {
  return metadata ? Math.max(0, metadata.requests_remaining - localReservations) : 0;
}
function expired() { return !metadata || Date.now() >= metadata.expiresAt; }
function usable() {
  return !IS_RESEARCH_MIRROR && metadata !== null && metadata.status === 'ready' && !expired() && remaining() > 0 && storageUsable && typeof globalThis.crypto?.randomUUID === 'function';
}
function updateControls() {
  const allowed = usable() && !checking && !pending && !unknown;
  $('prompt').disabled = !allowed;
  $('generate').disabled = !allowed || !$('prompt').value.trim();
  $('refresh-metadata').disabled = IS_RESEARCH_MIRROR || checking || pending;
  $('question').setAttribute('aria-busy', String(pending));
  $('generate').textContent = pending ? 'Waiting for the model…' : 'Ask original Granite →';
  $('unknown-attempt').hidden = unknown === null;
  $('new-question').disabled = !unknown || !$('new-question-ack').checked || pending;
  $('character-count').textContent = `${$('prompt').value.length} / ${metadata?.limits.max_input_chars ?? 2400} characters`;
  if (metadata) {
    $('trial-quota').textContent = `${remaining()} possible slots left of ${metadata.limits.max_requests} at the last availability check${localReservations ? ', less this page’s subsequent attempts' : ''}.`;
  }
  if (unknown) {
    $('answer-state').textContent = 'Completion unknown';
    $('request-id').textContent = unknown.request_id;
  }
}
function unavailable(title, message) {
  metadata = null;
  clearTimeout(expiryTimer);
  $('connection-title').textContent = title;
  $('connection-status').textContent = message;
  $('checkpoint').textContent = 'Not verified';
  $('trial-quota').textContent = 'Not verified';
  $('trial-expiry').textContent = 'Not verified';
}
function verifyMetadata(data) {
  if (!data || data.version !== 1 || data.service !== SERVICE || data.model !== MODEL || data.base_revision !== REVISION || data.variant !== 'base' || !Array.isArray(data.supported_variants) || data.supported_variants.length !== 1 || data.supported_variants[0] !== 'base' || data.checkpoint_improvement_established !== false || typeof data.checkpoint_id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(data.checkpoint_id)) throw new Error('The advertised checkpoint is not the supported original Granite model.');
  const limits = data.limits;
  const maximums = {max_requests: 20, max_input_chars: 2400, max_input_tokens: 768, max_output_tokens: 512, context_limit: 2048};
  if (!limits || Object.entries(maximums).some(([key, max]) => !Number.isInteger(limits[key]) || limits[key] < 1 || limits[key] > max) || limits.max_input_tokens + limits.max_output_tokens > limits.context_limit) throw new Error('The advertised request limits could not be verified.');
  if (!Number.isInteger(data.requests_consumed) || data.requests_consumed < 0 || data.requests_consumed > limits.max_requests || data.requests_remaining !== limits.max_requests - data.requests_consumed || data.status !== (data.requests_remaining === 0 ? 'quota_exhausted' : 'ready')) throw new Error('The shared trial availability could not be verified.');
  const expiresAt = Date.parse(data.expires_at_utc);
  if (!Number.isFinite(expiresAt) || expiresAt > Date.now() + 86460000) throw new Error('The bounded trial expiry could not be verified.');
  return {...data, expiresAt};
}
async function gatewayJSON(response) {
  if (!(response.headers.get('content-type') || '').toLowerCase().startsWith('application/json')) throw new Error('This host did not return the expected gateway response.');
  const text = await response.text();
  if (text.length > 65536) throw new Error('The gateway response exceeded the supported size.');
  return JSON.parse(text);
}
async function checkAvailability() {
  if (IS_RESEARCH_MIRROR) {
    $('mirror-notice').hidden = false;
    unavailable('Continue on GraniteQuery.live', 'Open the interactive trial using the link above. This copy keeps the published research available.');
    $('attempt-status').textContent = 'This research copy does not submit questions. Continue on the live site to use the trial.';
    updateControls();
    return;
  }
  if (checking || pending) return;
  checking = true;
  metadata = null;
  clearTimeout(expiryTimer);
  $('connection-title').textContent = 'Checking availability';
  $('connection-status').textContent = 'Reading gateway metadata. This does not request a model generation.';
  updateControls();
  try {
    const response = await fetch('/api/model', {headers: {Accept: 'application/json'}, cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(75000)});
    const data = await gatewayJSON(response);
    if (!response.ok) {
      const code = data?.version === 1 && data?.service === SERVICE ? data.error?.code : '';
      if (code === 'trial_expired') throw new Error('This inference trial has ended. No generation was requested.');
      if (code === 'origin_denied') throw new Error('Inference is not configured for this website address. No generation was requested.');
      if (code === 'not_configured') throw new Error('Interactive inference is not connected on this host. No generation was requested.');
      throw new Error('Availability could not be verified. No generation was requested.');
    }
    metadata = verifyMetadata(data);
    localReservations = 0;
    $('checkpoint').textContent = metadata.checkpoint_id + ' · original model';
    $('trial-expiry').textContent = new Date(metadata.expiresAt).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
    const cap = Math.min(OUTPUT_CAP, metadata.limits.max_output_tokens);
    $('output-limit').textContent = cap + ' output tokens on this page';
    $('generation-limit').textContent = `Up to ${cap} output tokens · greedy, non-thinking.`;
    $('prompt').maxLength = metadata.limits.max_input_chars;
    if (expired()) {
      $('connection-title').textContent = 'Trial ended';
      $('connection-status').textContent = 'The advertised expiry has passed. New submissions are disabled.';
    } else if (!remaining()) {
      $('connection-title').textContent = 'Shared quota exhausted';
      $('connection-status').textContent = 'The backend reports no trial slots remaining. New submissions are disabled.';
    } else {
      $('connection-title').textContent = 'Original Granite connected';
      $('connection-status').textContent = 'The gateway reports an available original-checkpoint trial. A submission may require a cold start; a successful answer is not guaranteed.';
      expiryTimer = setTimeout(() => {
        $('connection-title').textContent = 'Trial ended';
        $('connection-status').textContent = 'The advertised expiry has passed. New submissions are disabled.';
        updateControls();
      }, Math.max(0, metadata.expiresAt - Date.now()));
    }
    if (!pending && !unknown) $('attempt-status').textContent = usable() ? 'Ready for one explicit submission. No generation has been requested by this availability check.' : 'Submissions are disabled for this trial.';
  } catch (error) {
    unavailable('Inference unavailable', error.name === 'TimeoutError' ? 'The availability check timed out. You can deliberately refresh it; no generation was requested.' : error instanceof SyntaxError ? 'This host did not return valid gateway metadata. No generation was requested.' : error.message);
    if (!unknown) $('attempt-status').textContent = 'No generation was requested. Refresh availability to check the connection again.';
  } finally {
    checking = false;
    if (!storageUsable) $('attempt-status').textContent = 'Submissions are disabled because this browser cannot safely retain a request receipt in this tab. Enable session storage before trying inference.';
    if (typeof globalThis.crypto?.randomUUID !== 'function') $('attempt-status').textContent = 'Submissions require a secure browser context with request-ID support.';
    updateControls();
  }
}
function verifyGeneration(data, attempt, expected, cap) {
  return data?.version === 1 && data.service === SERVICE && data.status === 'completed' && data.model === MODEL && data.base_revision === REVISION && data.variant === 'base' && data.checkpoint_id === expected.checkpoint_id && data.request_id === attempt.request_id && typeof data.response === 'string' && data.response.length <= 32768 && typeof data.truncated === 'boolean' && Number.isInteger(data.generated_tokens) && data.generated_tokens >= 0 && data.generated_tokens <= cap && Number.isInteger(data.input_tokens) && data.input_tokens > 0 && data.input_tokens <= expected.limits.max_input_tokens && Number.isFinite(data.elapsed_seconds) && data.elapsed_seconds >= 0 && data.elapsed_seconds <= 240 && data.settings?.max_new_tokens === cap && data.settings?.enable_thinking === false && data.settings?.do_sample === false;
}
const failureCopy = {
  invalid_request: 'The gateway rejected the request format. No generation started.',
  invalid_prompt: 'The question does not meet the gateway’s prompt limits. No generation started.',
  invalid_token_limit: 'The output setting was rejected. No generation started.',
  invalid_request_id: 'The request ID was rejected. No generation started.',
  unsupported_variant: 'This host does not advertise the required original model. No generation started.',
  request_too_large: 'The question exceeds the request size limit. No generation started.',
  unsupported_media_type: 'The gateway rejected the request encoding. No generation started.',
  origin_denied: 'Inference is not configured for this website address. No generation started.',
  not_configured: 'Interactive inference is not connected on this host. No generation started.',
  trial_expired: 'The configured trial has ended. No new generation started.'
};
$('question').addEventListener('submit', async event => {
  event.preventDefault();
  if (!usable() || checking || pending || unknown) { updateControls(); return; }
  const prompt = $('prompt').value.trim();
  if (!prompt || prompt.length > metadata.limits.max_input_chars) return;
  const expected = metadata, cap = Math.min(OUTPUT_CAP, expected.limits.max_output_tokens);
  const attempt = {request_id: crypto.randomUUID(), started_at: new Date().toISOString(), completion: 'unknown', acknowledged: false};
  if (!saveAttempt(attempt)) {
    $('attempt-status').textContent = 'The request receipt could not be saved. Nothing was sent; submissions are disabled.';
    updateControls(); return;
  }
  pending = true;
  localReservations++;
  $('request-id').textContent = attempt.request_id;
  $('answer-state').textContent = 'Waiting for the model';
  $('response').textContent = 'Waiting for original Granite. A cold start can take several minutes. This request will not be automatically retried.';
  $('response-meta').textContent = '';
  $('attempt-status').textContent = 'One request sent. Keep this page open; reloading will preserve its uncertain receipt, not resend it.';
  updateControls();
  try {
    const response = await fetch('/api/generate', {method: 'POST', headers: {'Content-Type': 'application/json', Accept: 'application/json'}, cache: 'no-store', credentials: 'same-origin', body: JSON.stringify({prompt, variant: 'base', request_id: attempt.request_id, max_new_tokens: cap}), signal: AbortSignal.timeout(190000)});
    const data = await gatewayJSON(response);
    if (!response.ok) {
      if (data?.version === 1 && data.service === SERVICE && data.error?.retryable === false && data.error.completion === 'not_started') {
        localReservations = Math.max(0, localReservations - 1);
        saveAttempt({...attempt, completion: 'not_started'});
        $('answer-state').textContent = 'Request not started';
        $('response').textContent = failureCopy[data.error.code] || 'The gateway reports that no generation started. No automatic retry was attempted.';
        $('attempt-status').textContent = 'No generation started. Check the connection or edit the question before a deliberate new submission.';
        if (['not_configured', 'origin_denied', 'trial_expired', 'unsupported_variant'].includes(data.error.code)) unavailable('Connection unavailable', 'Refresh availability before submitting again.');
        return;
      }
      if (data?.version === 1 && data.service === SERVICE && ['quota_exhausted', 'trial_expired', 'checkpoint_mismatch'].includes(data.error?.code)) {
        unavailable(data.error.code === 'quota_exhausted' ? 'Shared quota exhausted' : 'Trial unavailable', 'The gateway reports that this trial cannot accept another request. Refresh availability before a new submission.');
      }
      throw new Error('The gateway could not confirm that this attempt completed or remained undispatched.');
    }
    if (!verifyGeneration(data, attempt, expected, cap)) throw new Error('The response did not match the pinned model and request receipt.');
    saveAttempt({...attempt, completion: 'completed'});
    $('answer-state').textContent = data.truncated ? 'Returned · output limit reached' : 'Returned';
    $('response').textContent = data.response || '(The model returned no text.)';
    $('response-meta').textContent = `${data.generated_tokens} output tokens · ${data.input_tokens} input tokens · ${data.truncated ? 'The response was truncated.' : 'The response was not truncated.'} Check the answer independently.`;
    $('attempt-status').textContent = 'This attempt returned. Another deliberate question creates a new request and can consume another shared slot.';
  } catch {
    unknown = attempt;
    saveAttempt(attempt);
    $('new-question-ack').checked = false;
    $('answer-state').textContent = 'Completion unknown';
    $('response').textContent = 'No verified answer is available. The request may still have run and consumed quota. It has not been replayed.';
    $('attempt-status').textContent = 'The attempt is locked to prevent replay. Its request ID is retained below.';
  } finally {
    pending = false;
    if (!storageUsable) $('attempt-status').textContent = 'The request receipt could not be updated in this tab. Submissions are disabled; keep the displayed request ID before leaving this page.';
    updateControls();
  }
});
$('prompt').addEventListener('input', updateControls);
$('refresh-metadata').addEventListener('click', checkAvailability);
$('new-question-ack').addEventListener('change', updateControls);
$('new-question').addEventListener('click', () => {
  if (!unknown || !$('new-question-ack').checked || pending) return;
  if (!saveAttempt({...unknown, acknowledged: true})) {
    $('attempt-status').textContent = 'Acknowledgement could not be saved. Nothing was sent; the previous request remains locked.';
    updateControls(); return;
  }
  unknown = null;
  $('new-question-ack').checked = false;
  $('prompt').value = '';
  $('answer-state').textContent = 'New question not sent';
  $('response').textContent = 'The previous uncertain attempt was acknowledged. Enter a different question; it will receive a new request ID only when you submit.';
  $('response-meta').textContent = '';
  $('attempt-status').textContent = 'No new request has been sent. The earlier request ID remains shown until your next deliberate submission.';
  updateControls();
  if (!$('prompt').disabled) $('prompt').focus();
});
if (unknown) {
  $('answer-state').textContent = 'Previous completion unknown';
  $('response').textContent = 'A previous request in this tab did not record a confirmed completion. It has not been sent again.';
  $('attempt-status').textContent = 'The previous attempt is locked. Review the acknowledgement before starting a different question.';
}
updateControls();
// One initial metadata check; no polling, generation, or hidden retry loop.
checkAvailability();
