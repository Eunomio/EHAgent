<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  api,
  type CurrentTaskResponse,
  type FeedbackAction,
  type HealthResponse,
  type RiskTask,
} from '@/api/client'

const health = ref<HealthResponse | null>(null)
const current = ref<CurrentTaskResponse | null>(null)
const error = ref('')
const busy = ref(false)
const confirmation = ref<FeedbackAction | null>(null)
const notice = ref('')

const task = computed(() => current.value?.task || null)
const actionable = computed(() => ['OPEN', 'DEFERRED'].includes(task.value?.status || ''))

const statusCopy: Record<string, string> = {
  OPEN: '需要处理',
  DEFERRED: '已经安排稍后提醒',
  RESCAN_PENDING: '等待复查',
  RESOLVED: '已经处理完成',
  DISPUTED: '已记录为没有风险',
  PAUSED: '此类提醒已暂停',
}

const actionCopy: Record<FeedbackAction, { label: string; confirm: string }> = {
  DONE: { label: '我已处理', confirm: '确认已经把物品移开了吗？' },
  DEFER: { label: '稍后提醒', confirm: '确认在30分钟后再提醒吗？' },
  NOT_A_RISK: { label: '这里没有风险', confirm: '确认这里的摆放是安全的吗？' },
  PAUSE: { label: '暂停此类提醒', confirm: '确认暂停同类演示提醒吗？' },
}

async function load() {
  error.value = ''
  try {
    ;[health.value, current.value] = await Promise.all([api.health(), api.currentTask()])
  } catch {
    error.value = '暂时无法读取本地服务，请联系家人或工程人员。'
  }
}

async function submit(action: FeedbackAction) {
  if (!task.value) return
  busy.value = true
  try {
    const result = await api.submitFeedback(task.value.task_id, action)
    current.value = { task: result.task, message: result.message, checked_at: new Date().toISOString() }
    notice.value = result.message
    confirmation.value = null
  } catch {
    notice.value = '这次操作没有保存成功，请再试一次。'
  } finally {
    busy.value = false
  }
}

function speakTask(value: RiskTask) {
  if (!('speechSynthesis' in window)) {
    notice.value = '当前浏览器不支持语音朗读。'
    return
  }
  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(
    `${value.title}。${value.explanation}。建议：${value.suggested_action}`,
  )
  utterance.lang = 'zh-CN'
  utterance.rate = 0.85
  window.speechSynthesis.speak(utterance)
}

onMounted(load)
</script>

<template>
  <section class="resident-home" aria-labelledby="resident-title">
    <div class="resident-intro">
      <div>
        <p class="eyebrow">今天需要关注</p>
        <h1 id="resident-title">{{ task ? '先处理这一件事' : '现在没有待处理事项' }}</h1>
      </div>
      <button class="refresh-button" type="button" @click="load">重新查看</button>
    </div>

    <div v-if="error" class="resident-alert" role="alert">{{ error }}</div>

    <article v-else-if="task" class="resident-task-card" aria-live="polite">
      <div class="demo-ribbon">
        <strong>演示任务 · 不是真实风险</strong>
        <span>来源：{{ task.source_type === 'REPLAY' ? '内置回放素材' : '人工标注素材' }}</span>
      </div>

      <div class="task-main">
        <figure v-if="task.evidence_url" class="evidence-figure">
          <img :src="task.evidence_url" :alt="`风险证据：${task.evidence_label}`" />
          <figcaption>画面仅用于本机演示</figcaption>
        </figure>

        <div class="task-copy">
          <div class="task-meta">
            <span class="risk-badge">需要注意</span>
            <span>{{ task.location }}</span>
            <span>{{ statusCopy[task.status] }}</span>
          </div>
          <h2>{{ task.title }}</h2>
          <p class="plain-reason">{{ task.explanation }}</p>
          <div class="suggestion-box">
            <span aria-hidden="true">✓</span>
            <p><strong>建议这样做</strong>{{ task.suggested_action }}</p>
          </div>
          <button class="speak-button" type="button" @click="speakTask(task)">🔊 朗读这条提醒</button>
        </div>
      </div>

      <div v-if="notice" class="action-notice" role="status">{{ notice }}</div>

      <template v-if="actionable">
        <div v-if="confirmation" class="confirmation-panel" role="alertdialog" aria-modal="true">
          <strong>{{ actionCopy[confirmation].confirm }}</strong>
          <div>
            <button class="primary-action" type="button" :disabled="busy" @click="submit(confirmation)">
              {{ busy ? '正在保存…' : '确认' }}
            </button>
            <button type="button" :disabled="busy" @click="confirmation = null">返回</button>
          </div>
        </div>

        <div v-else class="resident-actions" aria-label="请选择处理方式">
          <button class="primary-action" type="button" @click="confirmation = 'DONE'">
            <strong>我已处理</strong><span>物品已经移开</span>
          </button>
          <button type="button" @click="confirmation = 'DEFER'">
            <strong>稍后提醒</strong><span>30分钟后再说</span>
          </button>
          <button type="button" @click="confirmation = 'NOT_A_RISK'">
            <strong>这里没有风险</strong><span>记录我的判断</span>
          </button>
          <button type="button" @click="confirmation = 'PAUSE'">
            <strong>暂停此类提醒</strong><span>不再主动打扰</span>
          </button>
        </div>
      </template>

      <div v-else class="task-status-panel" :class="task.status.toLowerCase()">
        <strong>{{ statusCopy[task.status] }}</strong>
        <p v-if="task.status === 'RESCAN_PENDING'">请在工程测试台运行“整改后的通畅走廊”素材完成复查。</p>
        <p v-else-if="task.status === 'RESOLVED'">谢谢您，走廊通行位置已经恢复。</p>
        <p v-else>您的选择已经保存，不需要继续操作。</p>
      </div>
    </article>

    <article v-else class="empty-state">
      <div class="empty-icon" aria-hidden="true">✓</div>
      <h2>还没有演示任务</h2>
      <p>请先让工程人员在测试台选择一份素材运行Agent。本页面不会把“没有测试结果”说成“当前安全”。</p>
      <a href="/engineering">进入工程测试台</a>
    </article>

    <footer v-if="health" class="resident-service-status">
      <span class="status-dot" :class="health.status"></span>
      本地服务{{ health.status === 'ok' ? '正常' : '需要检查' }} · v{{ health.version }}
    </footer>
  </section>
</template>
