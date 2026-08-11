<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="engineering-shell">
    <header class="topbar engineering-bar">
      <strong>居安Agent 工程控制台</strong>
      <nav><a href="/">返回住户端</a></nav>
    </header>
    <main class="page-content"><RouterView /></main>
  </div>
</template>
