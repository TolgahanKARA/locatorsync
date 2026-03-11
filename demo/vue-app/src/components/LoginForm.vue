<template>
  <div class="login-container">
    <h1 class="login-title">Giriş Yap</h1>

    <!-- GOOD: data-test var -->
    <input
      v-model="username"
      type="text"
      class="form-control input-username"
      placeholder="Kullanıcı adı"
      data-test="username-input"
      name="username"
    />

    <!-- BAD: data-test yok, sadece class -->
    <input
      v-model="password"
      type="password"
      class="form-control input-password"
      placeholder="Şifre"
    />

    <!-- BAD: data-test yok, UI library class -->
    <button
      class="el-button el-button--primary btn-login"
      @click="handleLogin"
    >
      Giriş Yap
    </button>

    <!-- GOOD: data-test var -->
    <button
      class="btn btn-link"
      data-test="forgot-password-link"
      @click="goToForgotPassword"
    >
      Şifremi Unuttum
    </button>

    <!-- BAD: data-test yok, sadece text -->
    <a href="/register" class="register-link">
      Kayıt Ol
    </a>

    <!-- GOOD: aria-label var (orta stabilite) -->
    <button
      aria-label="Kapat"
      class="close-btn icon-btn"
      @click="closeModal"
    >
      ✕
    </button>
  </div>
</template>

<script>
export default {
  name: 'LoginForm',
  data() {
    return {
      username: '',
      password: '',
    }
  },
  methods: {
    handleLogin() { /* ... */ },
    goToForgotPassword() { /* ... */ },
    closeModal() { /* ... */ },
  }
}
</script>
