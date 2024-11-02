from itertools import product
from django.http import HttpResponse, JsonResponse
from django.template import loader
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.paginator import Paginator
from .models import Producto, Categoria, Pedido, DetallePedido
from .forms import RegistroUsuarioForm, PedidoForm, DireccionEnvioForm, ClienteForm, DetallePedidoForm

# Vista para la página de inicio
def inicio(request):
    productos_destacados = Producto.objects.filter(disponible=True)[:4]  # Ejemplo de productos destacados
    return render(request, 'inicio.html', {'productos_destacados': productos_destacados})

# Vista para la página de productos
def productos(request):
    productos = Producto.objects.filter(disponible=True)

    # Filtrar por categoría
    categoria = request.GET.get('categoria')
    if categoria:
        productos = productos.filter(categoria__nombre=categoria)

    # Filtrar por precio
    precio = request.GET.get('precio')
    if precio:
        productos = productos.filter(precio__lte=precio)

    # Paginación: 12 productos por página
    paginator = Paginator(productos, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'productos.html', {'page_obj': page_obj})

# Vista para ver los detalles de un producto
def detalle_producto(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    return render(request, 'detalle_producto.html', {'producto': producto})

# Vista para registrar usuarios
def registro(request):
    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            login(request, user)
            return redirect('inicio')
    else:
        form = RegistroUsuarioForm()
    return render(request, 'registro.html', {'form': form})

# Vista para iniciar sesión
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                
                # Redirigir al carrito si es que estaba intentando realizar una compra
                next_url = request.GET.get('next', 'inicio')
                return redirect(next_url)
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})

# Vista para crear un pedido
@login_required
def crear_pedido(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    if request.method == 'POST':
        cantidad = int(request.POST.get('cantidad', 1))

        carrito = request.session.get('carrito', [])
        
        # Verificar si el producto ya está en el carrito
        producto_encontrado = False
        for item in carrito:
            if item['producto_id'] == producto.id:
                item['cantidad'] += cantidad
                producto_encontrado = True
                break

        if not producto_encontrado:
            carrito.append({
                'producto_id': producto.id,
                'nombre': producto.nombre,
                'precio': float(producto.precio),
                'cantidad': cantidad
            })

        request.session['carrito'] = carrito
        request.session.modified = True

        return redirect('ver_carrito')
    else:
        return render(request, 'crear_pedido.html', {'producto': producto})

# Vista para ver el carrito de compras
@login_required
def ver_carrito(request):
    carrito = request.session.get('carrito', [])
    total_general = sum(item['precio'] * item['cantidad'] for item in carrito)

    productos_ids = [item['producto_id'] for item in carrito]
    productos = Producto.objects.filter(id__in=productos_ids)

    pedidos = []
    for item in carrito:
        producto = productos.get(id=item['producto_id'])
        pedidos.append({
            'producto': producto,
            'cantidad': item['cantidad'],
            'subtotal': producto.precio * item['cantidad'],
        })

    return render(request, 'carrito.html', {'pedidos': pedidos, 'total': total_general})

# Vista para finalizar compra
@login_required
def finalizar_compra(request):
    carrito = request.session.get('carrito', [])

    if not carrito:
        return redirect('nombre_de_la_vista_de_error')

    if request.method == 'POST':
        direccion_form = DireccionEnvioForm(request.POST)

        if direccion_form.is_valid():
            direccion_envio = direccion_form.save(commit=False)
            direccion_envio.usuario = request.user
            direccion_envio.save()

            pedido = Pedido.objects.create(
                usuario=request.user,
                direccion_envio=direccion_envio,
                estado='espera'
            )

            for item in carrito:
                DetallePedido.objects.create(
                    pedido=pedido,
                    producto_id=item['producto_id'],
                    cantidad=item['cantidad']
                )

            request.session['carrito'] = []

            return redirect('mi_cuenta')

    else:
        direccion_form = DireccionEnvioForm()

    return render(request, 'finalizar_compra.html', {
        'direccion_form': direccion_form,
        'carrito': carrito,
    })

# Vista para ver la cuenta del usuario
@login_required
def mi_cuenta(request):
    return render(request, 'mi_cuenta.html')

# Vista para ver los pedidos del usuario
@login_required
def pedidos_view(request):
    pedidos = Pedido.objects.filter(usuario=request.user).order_by('-fecha_pedido')
    return render(request, 'pedidos.html', {'pedidos': pedidos})

# Vista para actualizar un pedido (opcional)
@login_required
def actualizar_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, usuario=request.user)
    if request.method == 'POST':
        nueva_cantidad = int(request.POST.get('cantidad', 1))
        pedido.cantidad = nueva_cantidad
        pedido.save()
    return redirect('ver_carrito')

# Vista para eliminar un pedido
@login_required
def eliminar_pedido(request, producto_id):
    carrito = request.session.get('carrito', [])
    nuevo_carrito = [item for item in carrito if item['producto_id'] != producto_id]

    request.session['carrito'] = nuevo_carrito
    request.session.modified = True
    return redirect('ver_carrito')

# Vista para agregar al carrito
@login_required
def agregar_al_carrito(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    cantidad = int(request.POST.get('cantidad', 1))

    carrito = request.session.get('carrito', [])
    
    producto_encontrado = False
    for item in carrito:
        if item['producto_id'] == producto_id:
            item['cantidad'] += cantidad
            producto_encontrado = True
            break

    if not producto_encontrado:
        carrito.append({
            'producto_id': producto.id,
            'nombre': producto.nombre,
            'precio': producto.precio,
            'cantidad': cantidad
        })

    request.session['carrito'] = carrito
    request.session.modified = True
    return redirect('ver_carrito')

# Vista para ver detalles del pedido
@login_required
def detalle_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, usuario=request.user)
    return render(request, 'detalle_pedido.html', {'pedido': pedido})

# Vista para la confirmación del pedido
@login_required
def confirmacion_pedido(request, pedido_id):
    pedido = get_object_or_404(Pedido, id=pedido_id, usuario=request.user)
    return render(request, 'detalle_pedido.html', {'pedido': pedido})

# Vista para cerrar sesión
def custom_logout(request):
    logout(request)
    return redirect('inicio')  # Cambia 'inicio' al nombre de la vista que deseas redirigir después del cierre de sesión
