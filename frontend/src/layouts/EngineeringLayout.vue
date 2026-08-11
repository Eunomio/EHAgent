<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="engineering-shell">
    <header class="topbar engineering-bar">
      <div><strong>居安Agent 工程测试台</strong><small>Replay / Manual 垂直链路</small></div>
      <nav><a href="/" target="_blank">打开住户端预览 ↗</a></nav>
    </header>
    <main class="page-content"><RouterView /></main>
  </div>
</template>
