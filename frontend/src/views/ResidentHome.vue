<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api, type HealthResponse } from '@/api/client'

const health = ref<HealthResponse | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    health.value = await api.health()
  } catch {
    error.value = '暂时无法读取系统状态。'
  }
})
</script>

<template>
  <section aria-labelledby="resident-title">
    <p class="eyebrow">本地风险整改助手</p>
    <h1 id="resident-title">基础架构已准备</h1>
    <p class="lead">当前版本尚未连接萤石设备，也不会生成正式风险提醒。</p>

    <div class="status-card" aria-live="polite">
      <template v-if="health">
        <span class="status-dot" :class="health.status"></span>
        <div>
          <strong>本地服务 {{ health.status === 'ok' ? '运行正常' : '需要检查' }}</strong>
          <p>运行模式：{{ health.runtime_mode }} · 版本：{{ health.version }}</p>
        </div>
      </template>
      <p v-else>{{ error || '正在检查本地服务…' }}</p>
    </div>

    <div class="placeholder-task">
      <h2>后续版本将在这里显示整改任务</h2>
      <p>风险位置、可观察原因以及“已处理、稍后、不是风险、暂停”四个操作会集中展示。</p>
    </div>
  </section>
</template>
