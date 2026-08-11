<script setup lang="ts">
import { ref } from 'vue'
import { RouterView } from 'vue-router'

const fontScale = ref(Number(localStorage.getItem('resident-font-scale') || '1'))

function changeFont(delta: number) {
  fontScale.value = Math.min(1.25, Math.max(0.95, fontScale.value + delta))
  localStorage.setItem('resident-font-scale', String(fontScale.value))
}
</script>

<template>
  <div class="resident-shell" :style="{ '--resident-scale': fontScale }">
    <header class="topbar resident-topbar">
      <a class="brand" href="/" aria-label="返回居安Agent首页">
        <span class="brand-mark" aria-hidden="true">安</span>
        <span><strong>居安Agent</strong><small>把风险说清楚，把事情做完</small></span>
      </a>
      <div class="font-controls" aria-label="调整文字大小">
        <button type="button" aria-label="缩小文字" @click="changeFont(-0.1)">小字</button>
        <button type="button" aria-label="放大文字" @click="changeFont(0.1)">大字</button>
      </div>
    </header>
    <main class="page-content resident-content"><RouterView /></main>
  </div>
</template>
