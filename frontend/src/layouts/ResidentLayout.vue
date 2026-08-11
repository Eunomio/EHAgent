<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="resident-shell">
    <header class="topbar">
      <strong>居安Agent</strong>
      <span>住户端</span>
    </header>
    <main class="page-content resident-content"><RouterView /></main>
  </div>
</template>
