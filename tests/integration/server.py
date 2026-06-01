"""
Integration Test Server for Vectra QA.

A Flask app that simulates a real web application for end-to-end testing.
Includes: homepage, login, contact form, API endpoints, dynamic content.

Usage:
    python tests/integration/server.py
    # Server runs on http://localhost:8765
"""

from flask import Flask, request, jsonify, session, render_template_string
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# In-memory "database"
users = {"test@example.com": "password123"}
products = [
    {"id": 1, "name": "Laptop", "price": 999.99, "stock": 5},
    {"id": 2, "name": "Mouse", "price": 29.99, "stock": 100},
    {"id": 3, "name": "Keyboard", "price": 79.99, "stock": 0},
]
carts = {}  # session_id -> {product_id: quantity}


@app.route("/")
def homepage():
    """Homepage with navigation."""
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <title>Test Store - Ana Sayfa</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            nav { background: #333; padding: 10px; margin-bottom: 20px; }
            nav a { color: white; margin-right: 15px; text-decoration: none; }
            .product { border: 1px solid #ddd; padding: 15px; margin: 10px 0; }
            .price { color: #e74c3c; font-size: 1.2em; font-weight: bold; }
            button { background: #3498db; color: white; border: none; padding: 10px 20px; cursor: pointer; }
            button:disabled { background: #95a5a6; }
        </style>
    </head>
    <body>
        <nav>
            <a href="/">Ana Sayfa</a>
            <a href="/products">Ürünler</a>
            <a href="/cart">Sepet (<span id="cart-count">0</span>)</a>
            <a href="/login">Giriş Yap</a>
            <a href="/contact">İletişim</a>
        </nav>
        
        <h1>Hoş Geldiniz! Test Store</h1>
        <p>Türkçe karakter testi: ç, ğ, ı, ö, ş, ü</p>
        <p>Fiyat: <span class="price">₺100,00</span></p>
        
        <div class="cookie-banner" style="position: fixed; bottom: 0; background: #333; color: white; padding: 15px; width: 100%;">
            Bu site çerezleri kullanır. 
            <button class="accept-cookies">Kabul Et</button>
            <button class="reject-cookies">Reddet</button>
        </div>
    </body>
    </html>
    """)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Login page with form validation."""
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")

        if email in users and users[email] == password:
            session["user_id"] = email
            session["logged_in"] = True
            return jsonify({"success": True, "message": "Giriş başarılı!"})
        else:
            return jsonify({"success": False, "message": "Geçersiz e-posta veya şifre"}), 401

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><title>Giriş Yap</title></head>
    <body>
        <h1>Giriş Yap</h1>
        <form method="POST" action="/login">
            <input type="email" name="email" placeholder="E-posta" required><br>
            <input type="password" name="password" placeholder="Şifre" required><br>
            <button type="submit" data-login-button>Giriş Yap</button>
        </form>
    </body>
    </html>
    """)


@app.route("/logout")
def logout():
    """Logout endpoint."""
    session.clear()
    return jsonify({"success": True, "message": "Çıkış yapıldı"})


@app.route("/products")
def products_page():
    """Product listing page."""
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Ürünler</title></head>
    <body>
        <h1>Ürünler</h1>
    """
    for p in products:
        stock_status = "Stokta" if p["stock"] > 0 else "Stokta Yok"
        disabled = "disabled" if p["stock"] == 0 else ""
        html += f"""
        <div class="product" data-product-id="{p['id']}">
            <h2 class="product-name">{p['name']}</h2>
            <p class="price current-price">₺{p['price']}</p>
            <p class="stock-status">{stock_status}</p>
            <button class="add-to-cart" data-add-to-cart {disabled}>Sepete Ekle</button>
        </div>
        """
    html += "</body></html>"
    return html


@app.route("/api/cart/add", methods=["POST"])
def add_to_cart():
    """API endpoint to add item to cart."""
    data = request.get_json() or request.form
    product_id = int(data.get("product_id", 0))

    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        return jsonify({"success": False, "error": "Ürün bulunamadı"}), 404

    if product["stock"] <= 0:
        return jsonify({"success": False, "error": "Stokta yok"}), 400

    session_id = session.get("_id", request.cookies.get("session", "anonymous"))
    if session_id not in carts:
        carts[session_id] = {}

    carts[session_id][product_id] = carts[session_id].get(product_id, 0) + 1

    return jsonify(
        {
            "success": True,
            "cart": carts[session_id],
            "total_items": sum(carts[session_id].values()),
        }
    )


@app.route("/api/cart")
def get_cart():
    """Get current cart."""
    session_id = session.get("_id", request.cookies.get("session", "anonymous"))
    cart = carts.get(session_id, {})
    return jsonify({"cart": cart, "total_items": sum(cart.values())})


@app.route("/cart")
def cart_page():
    """Cart page."""
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><title>Sepet</title></head>
    <body>
        <h1>Sepetiniz</h1>
        <div id="cart-items"></div>
        <button class="checkout" data-checkout>Ödeme Yap</button>
    </body>
    </html>
    """)


@app.route("/contact", methods=["GET", "POST"])
def contact():
    """Contact form with validation."""
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        errors = []
        if not name:
            errors.append("İsim gerekli")
        if not email or "@" not in email:
            errors.append("Geçerli e-posta gerekli")
        if not message or len(message) < 10:
            errors.append("Mesaj en az 10 karakter olmalı")

        if errors:
            return jsonify({"success": False, "errors": errors}), 400

        return jsonify({"success": True, "message": "Mesajınız gönderildi!"})

    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head><title>İletişim</title></head>
    <body>
        <h1>İletişim</h1>
        <form method="POST" action="/contact" id="contact-form">
            <input type="text" name="name" placeholder="İsim" required><br>
            <input type="email" name="email" placeholder="E-posta" required><br>
            <textarea name="message" placeholder="Mesajınız" required minlength="10"></textarea><br>
            <button type="submit">Gönder</button>
        </form>
    </body>
    </html>
    """)


@app.route("/api/products")
def api_products():
    """REST API for products."""
    return jsonify({"products": products})


@app.route("/api/user")
def api_user():
    """Get current user info."""
    if session.get("logged_in"):
        return jsonify({"logged_in": True, "email": session.get("user_id")})
    return jsonify({"logged_in": False})


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8765, debug=True)
