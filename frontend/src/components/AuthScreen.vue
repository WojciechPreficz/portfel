<script setup lang="ts">
  import { ref } from 'vue';

  const emit = defineEmits<{
    submit: [password: string];
  }>();

  defineProps<{
    checking: boolean;
    submitting: boolean;
    message: string;
  }>();

  const password = ref('');

  const submit = () => {
    if (!password.value) return;
    emit('submit', password.value);
  };
</script>

<template>
  <main class="auth-shell">
    <section class="auth-card">
      <div class="auth-brand">
        <span class="brand-mark">P</span>
        <span>Portfel</span>
      </div>
      <p class="eyebrow">PRYWATNY DOSTĘP</p>
      <h1>{{ checking ? 'Sprawdzam sesję' : 'Zaloguj się' }}</h1>
      <p v-if="checking" class="auth-description">Sprawdzam, czy jesteś zalogowany.</p>
      <form v-else class="auth-form" @submit.prevent="submit">
        <label for="auth-password">Hasło</label>
        <input
          id="auth-password"
          v-model="password"
          type="password"
          autocomplete="current-password"
          required
          autofocus
        />
        <p v-if="message" class="auth-message" role="alert">{{ message }}</p>
        <button class="button button-primary auth-submit" type="submit" :disabled="submitting">
          {{ submitting ? 'Loguję...' : 'Zaloguj' }}
        </button>
      </form>
    </section>
  </main>
</template>
