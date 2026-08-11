<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api, type RuntimeState } from '@/api/client'

const runtime = ref<RuntimeState | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    runtime.value = await api.runtime()
  } catch {
    error.value = '无法读取运行模式。'
  }
})
</script>

<template>
  <section>
    <p class="eyebrow">仅限本机工程人员</p>
    <h1>工程控制台骨架</h1>
    <p class="lead">设备联调、区域标定和测试数据源将在后续版本进入此入口。</p>
    <div class="grid">
      <article class="panel">
        <h2>运行模式</h2>
        <p>{{ runtime?.mode || error || '读取中…' }}</p>
      </article>
      <article class="panel"><h2>摄像机</h2><p>未接入</p></article>
      <article class="panel"><h2>Replay数据</h2><p>等待本地素材</p></article>
    </div>
  </section>
</template>
