from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///snoopy.db'
app.secret_key = 'snoopy'
db = SQLAlchemy(app)






class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_height = db.Column(db.Integer, nullable=False)
    tickets = db.relationship('Tickets', backref='category', lazy=True)

class Tickets(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20))
    time = db.Column(db.String(20))
    title = db.Column(db.String(100))
    short_description = db.Column(db.Text)
    description = db.Column(db.Text)
    price = db.Column(db.Float)
    url = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    items = db.relationship('CartItem', backref='cart', lazy=True, cascade='all, delete-orphan')

class CartItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('cart.id'), nullable=False)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    ticket = db.relationship('Tickets', backref='cart_items')

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    cart = db.relationship('Cart', backref='user', lazy=True, uselist=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)







def get_or_create_cart():
    if 'user_email' in session:
        user = User.query.filter_by(email=session['user_email']).first()
        if user:
            cart = Cart.query.filter_by(user_id=user.id).first()
            if not cart:
                cart = Cart(user_id=user.id)
                db.session.add(cart)
                db.session.commit()
            return cart
    return None

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Проверяем, существует ли пользователь
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return 'Email already registered'
        
        # Создаем нового пользователя
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # Получаем id пользователя
        
        # Создаем корзину для нового пользователя
        cart = Cart(user_id=user.id)
        db.session.add(cart)
        
        # Если в сессии есть временная корзина, переносим товары
        if 'cart' in session and session['cart']:
            for item in session['cart']:
                cart_item = CartItem(
                    cart_id=cart.id,
                    ticket_id=item['id'],
                    quantity=item['quantity']
                )
                db.session.add(cart_item)
            session.pop('cart', None)
        
        try:
            db.session.commit()
            session['user_email'] = email
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            return 'There was an error adding your account'
    else:
        return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            session['user_email'] = email
            
            # Перенос товаров из временной корзины в постоянную
            if 'cart' in session and session['cart']:
                cart = get_or_create_cart()
                if cart:
                    for item in session['cart']:
                        cart_item = CartItem.query.filter_by(cart_id=cart.id, ticket_id=item['id']).first()
                        if cart_item:
                            cart_item.quantity += item['quantity']
                        else:
                            cart_item = CartItem(cart_id=cart.id, ticket_id=item['id'], quantity=item['quantity'])
                            db.session.add(cart_item)
                    db.session.commit()
                session.pop('cart', None)
            
            return redirect(url_for('index'))
        else:
            return 'Invalid email or password'
    else:
        return render_template('login.html')
            
@app.route('/basket')
def basket():
    cart_items = []
    total_price = 0.0

    if 'user_email' in session:
        user = User.query.filter_by(email=session['user_email']).first()
        if user and user.cart:
            for item in user.cart.items:
                item_total = item.quantity * item.ticket.price
                cart_items.append({
                    'ticket': item.ticket,
                    'quantity': item.quantity,
                    'total': item_total,
                    'id': item.id
                })
                total_price += item_total
    else:
        if 'cart' in session:
            cart = session['cart']
            ticket_ids = [item['id'] for item in cart]
            tickets = Tickets.query.filter(Tickets.id.in_(ticket_ids)).all()

            for item in cart:
                ticket = next((t for t in tickets if t.id == item['id']), None)
                if ticket:
                    item_total = item['quantity'] * ticket.price
                    cart_items.append({
                        'ticket': ticket,
                        'quantity': item['quantity'],
                        'total': item_total,
                        'id': ticket.id
                    })
                    total_price += item_total

    return render_template('basket.html', cart_items=cart_items, total_price=total_price)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    ticket_id = int(request.form['ticket_id'])
    quantity = int(request.form['quantity'])

    if 'user_email' not in session:
        if 'cart' not in session:
            session['cart'] = []
        cart = session['cart']
        # Обработка временной корзины в сессии для неавторизованных пользователей
        found = False
        for item in cart:
            if item['id'] == ticket_id:
                item['quantity'] += quantity
                found = True
                break
        if not found:
            cart.append({'id': ticket_id, 'quantity': quantity})
        session.modified = True
    else:
        # Обработка корзины в базе данных для авторизованных пользователей
        user = User.query.filter_by(email=session['user_email']).first()
        if user:
            cart = get_or_create_cart()
            if cart:
                cart_item = CartItem.query.filter_by(cart_id=cart.id, ticket_id=ticket_id).first()
                if cart_item:
                    cart_item.quantity += quantity
                else:
                    cart_item = CartItem(cart_id=cart.id, ticket_id=ticket_id, quantity=quantity)
                    db.session.add(cart_item)
                db.session.commit()

    return redirect(request.referrer or url_for('index'))

@app.route('/cart/update/<int:item_id>', methods=['POST'])
def update_cart(item_id):
    quantity = int(request.form.get('quantity', 1))
    if quantity < 1:
        quantity = 1

    if 'user_email' not in session:
        if 'cart' in session:
            cart = session['cart']
            for item in cart:
                if item['id'] == item_id:
                    item['quantity'] = quantity
                    break
            session.modified = True
    else:
        cart_item = CartItem.query.get(item_id)
        if cart_item and cart_item.cart.user.email == session['user_email']:
            cart_item.quantity = quantity
            db.session.commit()

    return redirect(url_for('basket'))

@app.route('/cart/remove/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    if 'user_email' not in session:
        if 'cart' in session:
            session['cart'] = [item for item in session['cart'] if item['id'] != item_id]
            session.modified = True
    else:
        cart_item = CartItem.query.get(item_id)
        if cart_item and cart_item.cart.user.email == session['user_email']:
            db.session.delete(cart_item)
            db.session.commit()

    return redirect(url_for('basket'))

@app.route('/')
@app.route('/index')
def index():
    categories = Category.query.all()
    return render_template('index.html', categories=categories)

@app.route('/opera')
def opera():
    tickets = Tickets.query.filter_by(category_id=1).all()
    return render_template("opera.html", tickets=tickets)

@app.route('/ticket/<int:ticket_id>')
def ticket_description(ticket_id):
    ticket = Tickets.query.get_or_404(ticket_id)
    return render_template('ticket_description.html', ticket=ticket)

@app.route('/art')
def art():
    tickets = Tickets.query.filter_by(category_id=2).all()
    return render_template("art.html", tickets=tickets)

@app.route('/tour')
def tour():
    tickets = Tickets.query.filter_by(category_id=3).all()
    return render_template("tour.html", tickets=tickets)

def get_cart_count():
    if 'user_email' in session:
        user = User.query.filter_by(email=session['user_email']).first()
        if user and user.cart:
            return sum(item.quantity for item in user.cart.items)
    elif 'cart' in session:
        return sum(item['quantity'] for item in session['cart'])
    return 0

@app.context_processor
def utility_processor():
    return dict(get_cart_count=get_cart_count)

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Добавляем категории, если их нет
        if Category.query.count() == 0:
            categories = [
                Category(
                    name='Opera',
                    slug='opera',
                    description='Great voices, powerful emotions! Opera tickets are your ticket to the world of high drama and unsurpassed music.',
                    image_height=231
                ),
                Category(
                    name='Art & Museum',
                    slug='art',
                    description='From classical to avant-garde: tickets to exhibitions and performances. Inspiration is waiting for you – keep up with new impressions!',
                    image_height=211
                ),
                Category(
                    name='Tours',
                    slug='tour',
                    description='Travel with music! Tickets to the festivals of the world – from Coachella to Glastonbury. Your adrenaline and the rhythm of summer.',
                    image_height=232
                )
            ]
            db.session.add_all(categories)
            db.session.commit()
        
        # Добавляем тестовые билеты, если их нет
        if Tickets.query.count() == 0:
            opera_category = Category.query.filter_by(slug='opera').first()
            test_tickets = [
                Tickets(
                    date="30 May",
                    time="19:00",
                    title="Salome Richard Strauss",
                    short_description="Premiere of Richard Strauss's controversial opera Salome.",
                    description="The premiere of Richard Strauss's one-act opera Salome took place at the Royal Opera House in Dresden on December 9, 1905. "
                                "The performance – conducted by Ernst von Schuch with an orchestra increased to one hundred and twenty musicians and a brilliant cast of soloists, including the famous Wagnerian singers Maria Wittich (Salome), Karel Burian (Herod) and Karl Parron (Jokanaan) – was considered outstanding by the composer. "
                                "The scandalous reputation of Oscar Wilde's play (1891), which served as the basis for the libretto written by the composer himself, further fueled interest in the new opera. Already in 1906, Salome appeared on the stages of sixteen European opera houses... "
                                "The Austrian premiere, which took place in 1906 in Graz under the baton of the composer, gathered the cream of the musical world: Gustav Mahler, Giacomo Puccini, Arnold Schoenberg and Alban Berg were present in the hall.",
                    price=50.00,
                    url="/ticket/1",
                    category_id=opera_category.id
                ),
                Tickets(
                    date="24 August",
                    time="19:00",
                    title="Traviata Giuseppe Verdi",
                    short_description="La Traviata is one of Verdi's most beloved operas.",
                    description="The premiere of the opera La Traviata took place on March 6, 1853, at the La Fenice Theatre in Venice. "
                                "For the first time, Verdi turned not to romantic events of the past, but to a modern and, at that time, scandalous plot. "
                                "For a long time, censorship did not allow the incredibly popular novel by Alexandre Dumas fils to be staged on the dramatic stage. "
                                "The premiere of The Lady of the Camellias took place only in 1852. "
                                "According to Verdi's publisher and friend Leon Escudier, 'Verdi once attended a performance of The Lady of the Camellias, the plot struck him, and he felt the trembling of the strings of his lyre.' "
                                "The opera did not receive the warmest audience reception. However, even the \"failed\" opera was well received by the press. "
                                "For example, a critic for the newspaper \"Musical Italy\" wrote: 'At the performance of this opera, we felt as if we were at a performance of Dumas's own drama - so much so that it did not seem like music. "
                                "<...> From this moment onwards, people will go to the opera house to see Verdi's operas in the same way as they go to the drama theatre.'",
                    price=60.00,
                    url="/ticket/2",
                    category_id=opera_category.id
                ),
                Tickets(
                    date="16 October",
                    time="19:00",
                    title="Legend of Love Arif Melikov",
                    short_description="A romantic ballet based on the ancient Persian legend, choreographed by Yuri Grigorovich.",
                    description="The Legend of Love is Yuri Grigorovich's second ballet, which was first shown on March 23, 1961 at the Leningrad Kirov Opera and Ballet Theatre (now the Mariinsky Theatre). "
                                "The libretto, based on his own play of the same name, was written by playwright Nazim Hikmet, and the music was composed by Arif Melikov. "
                                "The sets and costumes were created by Simon Virsaladze. The Legend of Love cemented his creative partnership with Grigorovich, which began with his work on The Stone Flower. "
                                "From then on, until the artist's death, he would design all of the choreographer's productions. "
                                "The same artists who were involved in The Stone Flower performed in the central roles at the premiere: Irina Kolpakova (Shirin), Alexander Gribov (Ferkhad), Anatoly Gridin (Vizier), Anatoly Sapogov (Stranger). "
                                "The part of Queen Mekhmene Banu was danced by Olga Moiseyeva, and later Alla Osipenko, the first Mistress of the Copper Mountain in The Stone Flower, was introduced into it.",
                    price=90.00,
                    url="/ticket/3",
                    category_id=opera_category.id
                )
            ]
            db.session.add_all(test_tickets)
            db.session.commit()
            
    app.run(debug=True) 