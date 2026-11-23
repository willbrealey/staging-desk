<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'

const cases = ref([])
const chosenId = ref('')
const loadError = ref(false)
const view = ref('preview')
const language = ref('en')
const savedDecision = ref('')
const temporaryDecision = ref(false)
const handoffOpen = ref(false)
const reviewPanel = ref(null)
const memory = new Map()
const labels = { ready: 'Ready for review', blocked: 'Check failed', escalated: 'Engineering review' }
const checkLabels = { pass: 'Passed', fail: 'Failed', skipped: 'Skipped' }
const decisionLabels = { approved: 'Approved for staging', changes: 'Changes requested' }
const selected = computed(() => cases.value.find(item => item.id === chosenId.value))
const digest = computed(() => selected.value?.sha256)
const canDecide = computed(() => {
  const item = selected.value
  return item?.status === 'ready' && item.reviewer && item.after && /^[0-9a-f]{64}$/.test(item.sha256)
    && item.checks.length > 0 && item.checks.every(check => check.status === 'pass')
})
const resultName = computed(() => savedDecision.value ? decisionLabels[savedDecision.value] : '')
const handoff = computed(() => selected.value && [
  'Engineering handoff · Staging Desk',
  selected.value.title,
  'Request: ' + selected.value.request,
  'Routing reason: ' + selected.value.reason,
  'Source: ' + selected.value.source
].join('\n'))
const caseCount = computed(() => cases.value.length)
const stateWords = { en: 'English', de: 'Deutsch' }
const summary = computed(() => {
  const totals = selected.value.checks.reduce((counts, check) => {
    counts[check.status] += 1
    return counts
  }, { pass: 0, fail: 0, skipped: 0 })
  return Object.entries(totals).filter(([, value]) => value).map(([state, value]) => value + ' ' + checkLabels[state].toLowerCase()).join(' · ')
})
const fillCount = text => text.replaceAll('{count}', '3')
const storageKey = () => 'staging-desk.v1.' + digest.value

function readDecision() {
  savedDecision.value = ''
  temporaryDecision.value = false
  if (!canDecide.value) return
  try {
    const value = localStorage.getItem(storageKey())
    if (Object.hasOwn(decisionLabels, value)) savedDecision.value = value
  } catch {
    temporaryDecision.value = true
  }
  if (memory.has(storageKey())) {
    savedDecision.value = memory.get(storageKey())
    temporaryDecision.value = true
  }
}

function decide(value) {
  if (!canDecide.value) return
  try {
    if (value) localStorage.setItem(storageKey(), value)
    else localStorage.removeItem(storageKey())
    memory.delete(storageKey())
    temporaryDecision.value = false
  } catch {
    memory.set(storageKey(), value)
    temporaryDecision.value = true
  }
  savedDecision.value = value
}

function readHash() {
  const requestedId = window.location.hash.slice(1)
  chosenId.value = cases.value.find(item => item.id === requestedId)?.id || cases.value[0]?.id || ''
}

function chooseCase(id) {
  if (chosenId.value === id) return
  window.location.hash = id
  chosenId.value = id
}

function validCatalog(data) {
  const copy = x => x && ['en', 'de'].every(lang => typeof x[lang] === 'string')
  return Array.isArray(data) && data.length > 0 && new Set(data.map(x => x?.id)).size === data.length &&
    data.every(x => x && Object.hasOwn(labels, x.status) && ['id', 'title', 'request', 'source', 'reason'].every(key => typeof x[key] === 'string') &&
      copy(x.before) && (x.after === null || copy(x.after)) && Array.isArray(x.checks) &&
      x.checks.every(check => check && typeof check.name === 'string' && typeof check.detail === 'string' && Object.hasOwn(checkLabels, check.status)))
}

async function load() {
  loadError.value = false
  try {
    const reply = await fetch(import.meta.env.BASE_URL + 'cases.json')
    if (!reply.ok) throw new Error('Cases unavailable')
    const rows = await reply.json()
    if (!validCatalog(rows)) throw new Error('Invalid case catalogue')
    cases.value = rows
    readHash()
  } catch {
    loadError.value = true
  }
}

watch(chosenId, () => {
  view.value = 'preview'
  language.value = selected.value?.id === 'blocked' ? 'de' : 'en'
  handoffOpen.value = false
})
watch([canDecide, digest], readDecision)
onMounted(() => {
  window.addEventListener('hashchange', readHash)
  window.addEventListener('storage', readDecision)
  load()
})
onBeforeUnmount(() => {
  window.removeEventListener('hashchange', readHash)
  window.removeEventListener('storage', readDecision)
})
</script>

<template>
  <a class="skip-link" href="#review" @click.prevent="reviewPanel?.focus()">Skip to selected request</a>
  <header class="masthead">
    <div class="shell masthead-inner">
      <div class="brand"><span class="mark" aria-hidden="true"><i></i><i></i><i></i></span>Staging Desk</div>
      <nav class="external" aria-label="Project links"><a class="source-link ci-link" href="https://github.com/willbrealey/staging-desk/actions">CI runs</a><a class="source-link" href="https://github.com/willbrealey/staging-desk">View source <span aria-hidden="true">↗</span></a></nav>
    </div>
  </header>
  <main class="shell">
    <div class="page-intro">
      <div><p class="context">Product owner workspace</p><h1>Change review</h1></div>
      <p class="intro-text">Inspect agent-proposed copy for a bilingual training app and decide what is ready for staging.</p>
    </div>
    <p v-if="loadError" role="alert">The case catalogue could not be loaded. <button type="button" @click="load">Retry</button></p>
    <p v-else-if="!selected" role="status">Loading recorded cases…</p>
    <div v-else class="workspace">
      <aside class="queue" aria-label="Recorded change requests">
        <div class="queue-heading"><h2>Recorded cases</h2><span>{{ caseCount }}</span></div>
        <nav aria-label="Choose a change request">
          <button v-for="item in cases" :key="item.id" :data-case="item.id" type="button" class="case-link" :class="{ active: chosenId === item.id }"
            :aria-current="chosenId === item.id ? 'true' : undefined" @click="chooseCase(item.id)">
            <span class="case-name">{{ item.title }}</span>
            <span :class="['flag', item.status]"><i aria-hidden="true"></i>{{ labels[item.status] }}</span>
          </button>
        </nav>
        <p class="queue-note">Replay recorded runs. Review decisions stay in this browser.</p>
      </aside>
      <article ref="reviewPanel" id="review" class="review" tabindex="-1" aria-labelledby="case-title">
        <div class="case-top">
          <div class="case-origin"><span :class="['pill', selected.status]"><i aria-hidden="true"></i>{{ labels[selected.status] }}</span><span>{{ selected.source }}</span></div>
          <h2 id="case-title">{{ selected.title }}</h2>
          <h3 class="small-heading">Original request</h3>
          <blockquote>{{ selected.request }}</blockquote>
        </div>
        <div class="views" role="group" aria-label="Review view">
          <button type="button" :aria-pressed="view === 'preview'" @click="view='preview'">Copy preview</button>
          <button type="button" :aria-pressed="view === 'evidence'" @click="view='evidence'">Run evidence <span>{{ selected.checks.length }}</span></button>
        </div>
        <div v-if="view === 'preview'" class="content-panel">
          <template v-if="selected.after">
            <div class="panel-head">
              <div><h3>Compare wording</h3><p>Sample queue of three reports</p></div>
              <div class="language" role="group" aria-label="Preview language">
                <button v-for="(name, key) in stateWords" :key="key" type="button" :aria-pressed="language === key" :lang="key" @click="language=key">{{ name }}</button>
              </div>
            </div>
            <div class="comparison">
              <section class="copy-side"><h4>Current</h4><p :lang="language">{{ fillCount(selected.before[language]) }}</p></section>
              <section class="copy-side proposed"><h4>Proposed</h4><p :lang="language">{{ fillCount(selected.after[language]) }}</p></section>
            </div>
          </template>
          <div v-else class="empty-state"><h3>Routed to engineering</h3><p>This request has no copy proposal to review.</p></div>
        </div>
        <div v-else class="content-panel evidence">
          <div class="panel-head"><div><h3>Independent checks</h3><p>{{ summary }}</p></div></div>
          <ul class="checks">
            <li v-for="(check,index) in selected.checks" :key="index">
              <div><strong>{{ check.name }}</strong><p>{{ check.detail }}</p></div>
              <span :class="['check-status', check.status]">{{ checkLabels[check.status] }}</span>
            </li>
          </ul>
          <dl class="provenance">
            <div><dt>Case source</dt><dd>{{ selected.source }}</dd></div>
            <div v-if="selected.reviewer"><dt>Independent reviewer</dt><dd>{{ selected.reviewer }}</dd></div>
            <div v-if="selected.sha256"><dt>Review fingerprint</dt><dd><code>{{ selected.sha256 }}</code></dd></div>
          </dl>
        </div>
        <section class="decision">
          <h3>{{ selected.status === 'ready' ? 'Product owner decision' : 'Handoff' }}</h3>
          <p class="decision-text">{{ selected.reason }}</p>
          <div v-if="canDecide" aria-live="polite">
            <div v-if="!savedDecision" class="actions">
              <button type="button" class="primary" @click="decide('approved')">Approve for staging</button>
              <button type="button" class="secondary" @click="decide('changes')">Request changes</button>
            </div>
            <div v-else class="recorded"><span>{{ resultName }}</span><button type="button" class="text-button" @click="decide('')">Reset decision</button></div>
            <p class="local-note">{{ temporaryDecision ? 'Browser storage is unavailable. Decisions last for this visit.' : 'Decisions apply only to this recorded proposal in your browser.' }}</p>
          </div>
          <div v-else-if="selected.status === 'escalated'" class="handoff">
            <button type="button" class="secondary" :aria-expanded="handoffOpen" aria-controls="handoff-detail" @click="handoffOpen = !handoffOpen">Engineering handoff</button>
            <div v-if="handoffOpen" id="handoff-detail">
              <label for="handoff-text">Select and copy this handoff for engineering</label>
              <textarea id="handoff-text" readonly rows="5" :value="handoff" @focus="$event.target.select()"></textarea>
            </div>
          </div>
          <p v-else-if="selected.status === 'ready'" class="local-note">The evidence required for a local decision is incomplete.</p>
        </section>
      </article>
    </div>
  </main>
</template>
