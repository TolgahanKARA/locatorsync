<template>
  <div class="product-list">
    <!-- GOOD: data-test var -->
    <input
      v-model="searchQuery"
      type="text"
      data-test="search-input"
      class="search-field"
      placeholder="Ara..."
    />

    <!-- BAD: nth-child kullanımına yol açacak yapı, data-test yok -->
    <div class="product-grid">
      <div
        v-for="product in products"
        :key="product.id"
        class="product-card"
      >
        <h3 class="product-title">{{ product.name }}</h3>
        <p class="product-price">{{ product.price }} TL</p>

        <!-- BAD: data-test yok, sadece class -->
        <button class="btn-add-cart" @click="addToCart(product)">
          Sepete Ekle
        </button>

        <!-- BAD: data-test yok -->
        <button class="btn-detail" @click="viewDetail(product)">
          Detay
        </button>
      </div>
    </div>

    <!-- GOOD: id var -->
    <select id="sort-select" class="sort-dropdown" v-model="sortBy">
      <option value="price">Fiyata Göre</option>
      <option value="name">İsme Göre</option>
    </select>

    <!-- BAD: hiç selector yok, tamamen kırılgan -->
    <button @click="loadMore" v-if="hasMore">
      Daha Fazla Yükle
    </button>
  </div>
</template>

<script>
export default {
  name: 'ProductList',
  data() {
    return {
      searchQuery: '',
      sortBy: 'price',
      products: [],
      hasMore: true,
    }
  }
}
</script>
