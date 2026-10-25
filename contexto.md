```
Guía del proyecto
```
Sistema inteligente basado en inteligencia artificial para optimizar descuentos dinámicos en
alimentos perecederos
Santiago Forero Díaz
santiagoforerod.@academia.umb.edu.co
Johan Sebastián Martínez Rodríguez
johanmartinez.sr@academia.umb.edu.co
Bryan Andrés Puentes Vargas
bryanpuentes.av@academia.umb.edu.co
Universidad Manuela Beltrán
Docente: Juan José Osorio Tabares
Ingeniería de Software - Sistemas Distribuidos
Facultad de Ingeniería
Colombia
2026


## Tabla De Contenido



- Introducción
- Definiciones y Abreviaturas
- Equipo De Trabajo
- Problema o necesidad
- Propuesta de valor
- Objetivos
   - Objetivo General
   - Objetivos Específicos
- Población Objetivo
- Resultados de encuestas
- Alcance
- Diagrama De Gantt
- Resumen Del Producto
- Requisitos Y Requerimientos De Usuario
   - Requerimientos Funcionales Del Sistema.....................................................................
   - Requerimientos No Funcionales Del Sistema
- Interfaz Gráfica, Maquetación
   - Interfaz: Login
      - Tipografía
      - Paleta de colores
   - Interfaz: Dashboard, Principal Administrador
      - Tipografía
      - Paleta de colores
   - Interfaz: Principal Cliente
      - Tipografía
      - Paleta de colores
   - Interfaz: Facturas
      - Tipografía
      - Paleta de colores
- Estudio De Mercado
- Modelo de negocio
- Estrategia de marketing
- Pitch – Video
- Desarrollo E Implementación
   - Arquitectura de dos nodos y capas
   - Módulo: server/domain/riesgo.py
   - Módulo: server/application/riesgo_service.py
   - Módulo: server/application/venta_service.py
   - Módulo: server/security (sesiones, tokens y hashing)
   - Cliente: client/ (hilos de red, inactividad y eventos)
   - Modelo de datos (server/infrastructure/db/orm.py)
- Solución
- Proyección o impacto
- Conclusiones
- Referencias Bibliográficas


```
Sistema Inteligente Basado En Inteligencia Artificial Para Optimizar Descuentos
Dinámicos En Alimentos Perecederos
```
## Introducción

Hoy en día los supermercados y los locales comerciales de tipo cadena se
encuentran ante los grandes retos de gestionar productos perecederos que deben ser
manejados de manera óptima si no se desea enfrentar una merma de ingresos o una gestión
ineficaz que puede conducir a generar alimentos en estado de desecho cuando nos
acercamos específicamente a estos entornos comerciales o los consumidores que desean
mejorar la economía de compra nos enfrentamos a plantear una solución tecnológica en
este sentido nos interesa la solución de gestión de inventario por medio de la inteligencia
artificial, el objetivo del proyecto converge en un aplicativo que permita tomar decisiones
en tiempo real.

El problema específico que transcurre es la pérdida del valor en los productos donde
son sensibles al tiempo como puede ser el caso de productos de alimentación cerca de su
fecha de caducidad pese a ser productos óptimos para ser consumidos por el motivo de
pasar del umbral de la fecha de caducidad pierden su valor en plaza lo que alrededor de esta
cuestión genera pérdidas o en su momento le añade un grano más dentro de la gestión
basada en el desperdicio alimentario, la gestión de estos procesos que se utilizan en muchos
comercios se lleva a cabo con una mecánica u otras de baja eficiencia por este motivo hay
decisiones tomadas tardíamente o incorrectas y por ello estamos a favor de la oportunidad
de automatizar el proceso de gestionar descuentos variables al tiempo.


Diversos estudios recientes han abordado la problemática del desperdicio de
alimentos y la optimización de los inventarios aplicando nuevas tecnologías según Parfitt, J.
(2021) una gestión alimentaria puede mejorar de forma notable las pérdidas que se pueden
dar en la cadena de suministro de la misma manera, Dutta, P. (2020) sugiere el uso de
analítica de datos para tomar mejores decisiones empresariales. Zhang, Y. (2022) se ha
centrado en la inteligencia artificial para establecer sistemas de predicción de la demanda al
mismo tiempo, Kamble, S. (2021) pone de relieve el potencial que tienen las nuevas
tecnologías en la gestión de la logística. Finalmente, Baryannis, G. (2019) propone modelos
predictivos aplicados al ámbito de las cadenas de suministro todos estos estudios
contribuyen a la viabilidad del proyecto.

La forma de desarrollo del proyecto se establece mediante un modelo de Gantt en el
que se definen las fases de análisis, diseño, desarrollo y pruebas e implementación del
sistema garantiza la posibilidad de organizar el uso de recursos establecer tiempos cumplir
con los objetivos delimitados todo ello permitirá una solución estructurada y eficaz para el
desarrollo del sistema.


## Definiciones y Abreviaturas

**Abreviatura /
Término**

```
Definición
```
IA Inteligencia Artificial, tecnología utilizada para automatizar
procesos y apoyar la toma de decisiones.

UI Interfaz de Usuario, parte visual del sistema con la que
interactúan los usuarios.

BD Base de Datos, sistema encargado de almacenar y gestionar la
información del inventario y productos.

Stock Cantidad disponible de productos dentro del inventario.

Inventario Conjunto de productos almacenados y disponibles para la venta.

Descuento dinámico Reducción automática del precio de un producto según su
cercanía a la fecha de vencimiento.

Producto perecedero Producto que tiene una fecha límite de consumo o vencimiento.

Fecha de
vencimiento

```
Fecha límite en la que un producto puede ser consumido o
vendido en condiciones óptimas.
```
Sistema cliente-
servidor

```
Modelo donde un cliente solicita información y un servidor la
procesa y administra.
```
Aplicación de
escritorio

```
Software instalado localmente en un computador para realizar
funciones específicas.
```

Usuario
administrador

```
Persona encargada de gestionar inventarios, descuentos y
productos dentro del sistema.
```
Usuario comprador Cliente que visualiza productos en oferta y realiza compras.

Automatización Proceso mediante el cual tareas se realizan automáticamente sin
intervención constante del usuario.

Oferta Reducción temporal del precio de un producto para incentivar su
venta.

Prototipo funcional Versión inicial del sistema desarrollada para validar su
funcionamiento y viabilidad.

Supermercado Establecimiento comercial que vende productos de consumo
masivo y alimentos.

Supermercado
pequeño

```
Tienda de menor tamaño que comercializa productos básicos y
alimentos.
```
Gestión de
inventario

```
Control y administración de productos disponibles dentro de un
negocio.
```
Desperdicio de
alimentos

```
Pérdida de productos alimenticios que no son consumidos antes
de vencer.
```
SQL Lenguaje utilizado para gestionar bases de datos relacionales.

CRUD Operaciones básicas de Crear, Leer, Actualizar y Eliminar
registros en una base de datos.

Nodo Equipo o sistema operativo que ejecuta una parte del sistema. El
proyecto tiene dos: el servidor (Ubuntu sobre WSL2) y el cliente
(Windows).

API REST Interfaz HTTP con mensajes JSON mediante la cual el cliente pide
operaciones al servidor (FastAPI).

WebSocket Conexión persistente sobre TCP por la que el servidor envía
eventos al cliente sin que este los pida.

Token (JWT) Credencial firmada que el servidor entrega al iniciar sesión y que
el cliente envía en cada petición para identificarse.

Cierre por
inactividad

Cierre automático de la sesión cuando el usuario no interactúa
durante un tiempo que el administrador puede configurar.

argon2id Algoritmo de derivación de claves usado para guardar las
contraseñas de forma que no puedan leerse.


## Equipo De Trabajo

El equipo de trabajo del proyecto fue llevado a cabo por tres miembros que
desarrollan cada uno de ellos áreas específicas para cumplir con una buena construcción de
la propuesta de solución, Santiago Forero se encargó de la construcción y estructuración de
la documentación del proyecto la cual incluye el análisis, planteamiento y organización de
los diferentes apartados académicos y técnicos, Johan Martínez es el encargado de construir
el código backend, implementa la lógica del sistema, maneja los datos y el mecanismo
interno de la aplicación, mientras que Bryan Puentes es el encargado de construir el
frontend el encargado de diseñar e implementar la interfaz gráfica de la aplicación con el
fin de cumplir con el objetivo de que la interacción del usuario con la aplicación sea clara y
funcional la distribución de los roles permite que haya un trabajo organizado y colaborativo
para garantizar el cumplimiento de los objetivos del proyecto propuestos por el equipo de
trabajo.


## Problema o necesidad

La realidad que presenta el análisis nos ha quedado patente y es que una gran parte
de la oferta de supermercados se encuentra sufriendo una pérdida de ingresos por la
presencia de productos perecederos desaprovechados que no pueden ser vendidos antes de
su fecha de caducidad, esta situación no afecta únicamente a los supermercados pues
también está la parte de los consumidores y la parte del medio ambiente éste último pasa a
ser un motivo de más desperdicio de productos en perfecto estado para la venta, además, en
muchos supermercados los productos que están próximos a caducar reciben todavía un trato
manual lo que resta y dificulta la gestión del stock de productos y de las compras, en las
encuestas realizadas a unas 60 personas se concluyó que una gran parte de los encuestados
habituales de supermercados tienden a comprar ese tipo de productos, sobre todo a partir de
las opciones siempre y casi siempre lo que vierte a entender que es un hábito de consumo
fijo una mayoría de los encuestados comunican estar dispuesto(a) o dispuesto(a) totalmente
a querer comprar productos cercanos a su fecha de caducidad pero eso sí, apostando por el
producto con el descuento adecuado, la opinión mayoritaria fue que el ahorro es importante
o muy importante a la hora de adquirir comida en este sentido el precio de los alimentos es
para los consumidores una razón de peso por otro lado otra gran parte de los encuestados
manifestaron que confiarían o no confiarían completamente en un sistema automatizado
que aplicara descuentos según la fecha de caducidad del producto, se apreció también una
visión positiva respecto al medio ambiente dado que la mayoría de encuestados creen que
este tipo de práctica ayudaría a reducir el desperdicio de alimentos, estos hallazgos
permiten vislumbrar una necesidad real en el mercado y sirven de razón fundamentada para


la automatización de un sistema de gestión inteligente y automática para descuentos
dinámicos de productos perecederos.


## Propuesta de valor

La propuesta se encuentra orientada al diseño de un sistema inteligente que integre
la gestión conducida de descuentos de tipo dinámico sobre los alimentos perecederos, la
solución se servirá para identificar los productos que están a punto de caducar involucrando
una gestión automática de descuentos de manera que solicite rotar el inventario y llevar en
consecuencia a la disminución de pérdidas económicas en relación con los otros métodos
que pueden utilizarse se diferencia en que pone en un único lugar informático la
información y mejora la visualización de los productos que están en descuento pudiendo así
integrar una gestión más sencilla y estructurada en el caso de los supermercados.


## Objetivos

### Objetivo General

Realizar un sistema inteligente con inteligencia artificial que sea capaz de optimizar
la gestión del inventario mediante la aplicación de descuentos dinámicos en productos
perecederos.

### Objetivos Específicos

Realizar el análisis del estado del producto del inventario a fin de obtener niveles de
riesgo asociados a su caducidad.

Realizar el diseño de un modelo de inteligencia artificial que permita calcular
descuentos dinámicos de forma automática.

Realizar la aplicación de escritorio para la gestión, visualización y toma de
decisiones del inventario.


## Población Objetivo

La población objeto de estudio está constituida en gran medida por dos segmentos
de interés prioritario dentro del sector comercio y consumo, los supermercados que tienen
un elevado volumen de manejo de productos perecederos con un componente temporal por
estar sujetos a una fecha de caducidad y por el otro los consumidores que quieren acceder a
productos a un menor precio sin dejar de lado la calidad percibida de los alimentos a partir
del análisis de encuestas realizadas y analizadas cerca de 60 respuestas en esta etapa del
proyecto evidenciando que un 65% de los encuestados realiza compras frecuentes en
supermercados como un hábito de compra corriente y una relación directa con este tipo de
establecimientos también que un 45% está dispuesto a comprar productos próximos a
vencer aunque nos encontramos con un grupo de consumidores que sugiere una cierta
desconfianza a la hora de optar por este tipo de productos con respecto al ahorro cerca de
un 70% de los encuestados declara que lograr ahorrar al momento de compra de alimentos
es importante o muy importante corroborando así que el económico es un factor
determinante a la hora de toma de decisiones de compra en torno al 75% se mostró de
acuerdo en confiar en un sistema automatizado que aplique descuentos según la fecha de
vencimiento lo que indica una predisposición hacia soluciones tecnológicas con el objetivo
de optimizar la gestión comercial, en cuanto a la frecuencia con la que adquirirían
productos con descuento vinculado a la fecha de vencimiento la mayoría de las respuestas
se sitúan entre ocasionalmente y frecuentemente lo que evidencia un grado de interés
notable y de potencialidad para crecer en este mercado, más del 70% piensa que este tipo
de sistema ayudaría a reducir el desperdicio de alimentos lo que da de cuenta que no es sólo
de un interés económico sino también de una preocupación social y medioambiental en


torno al desperdicio de alimentos, en términos generales los resultados permiten concluir
que existe una aceptación favorable en la implementación del sistema propuesto y que éste
representa una alternativa viable en el propio mercado, incluso en términos tales que
podríamos a partir de hacer pruebas piloto en los establecimientos comerciales generar el
impacto en al menos un 10% del mercado objetivo.


## Resultados de encuestas

El análisis estadístico de las encuestas realizadas permite identificar una tendencia
positiva hacia la implementación del sistema de descuentos automáticos para productos
próximos a vencer.

De la pregunta sobre la disposición para adquirir alimentos próximos a su fecha de
caducidad se obtuvieron 62 respuestas y de esta cantidad un 37,1% de los encuestados
mostraron estar totalmente dispuesto(a) para su compra un 24,2% fueron contestados como
dispuesto(a) que da una aceptación favorable hacia este tipo de alimento del 61,3% un
33,9% se mostró estar poco dispuesto(a) a su compra y solamente un 4,8% estaban no
dispuesto(a) a su compra lo que demuestra que si bien quedaba un grupo de consumidores
que mostraban dudas o recelos hacia la compra de los alimentos próximos a su fecha de
caducidad el grupo mayor presentaba una imagen positiva a la compra de alimentos con
descuentos por caducidad corroborando el resultado de una oportunidad para desarrollar
estrategias de marketing enfocados a alimentos perecederos de precio rebajado.


Respecto a la importancia del ahorro al comprar alimentos los resultados indican
que la situación económica es un elemento determinante en el comportamiento de compra
de los consumidores donde el 46,8% de los encuestados lo considera muy importante y el
27,4% como importante esto es un total de respuestas que ascienden al 74,2% de respuestas
positivas, por otro lado el 22,6% de la gente considera que es un elemento poco importante
y el 3,2% de los encuestados piensa que tiene nada de importancia, este comportamiento
estadístico corrobora que las estrategias de descuentos y en nuestro caso la aplicación del
sistema que proponemos pueden ser un elemento muy atractivo para los consumidores y
por tanto es posible que la aceptación que pueda tener el sistema en el mercado pueda llegar
a ser alta, dado el ahorro que los usuarios pueden llegar a obtener.


Ya respecto del nivel de confianza hacia la automatización de los descuentos por
fechas de vencimiento los resultados presentan una aceptación peor pero también
significativa, en efecto el 43,5% de las respuestas afirmaron totalmente confiaría en dicho
sistema el 29,0% afirmaron que confiaría totalizando un 72,5% de respuestas positivas en la
automatización del proceso, por el contrario, el 21,0% afirmaron confiaría poco y el 6,5%
no confiaría, estadísticamente se demuestra una visión positiva respecto de la
automatización de los procesos de gestión comercial y control de inventarios los
consumidores demostrarían viabilidad en implementar sistemas de aplicación automática de
descuentos con tecnología.

Con relación a la percepción sobre la disminución del desperdicio de alimentos que
podría producir este tipo de sistema podemos ver que los datos obtenidos en la encuesta dan
cuenta de una elevada conciencia social y medioambiental de los encuestados, el 50,0% de
las respuestas da cuenta de la opción totalmente de acuerdo el 29,0% se decantó por de
acuerdo configurando entre ambas respuestas un 79,0% de aceptación positiva por otro lado
el 12,9% se situó en desacuerdo y el 8,1% en totalmente en desacuerdo es decir da cuenta
de una de las respuestas que menos aceptación tuvo, por lo que podemos interpretar la
mayoría de los consultados han asumido un impacto positivo de una herramienta como esta,


tanto en la práctica de los intercambios de alimentos y de puntos centrando unas bases tanto
económicas como medioambientales que refuercen la viabilidad social del proyecto.


## Alcance

El alcance del presente proyecto es el diseño y desarrollo de un sistema distribuido
de dos nodos (un servidor y una aplicación de escritorio cliente) para gestionar
automáticamente los inventarios de productos perecederos de
supermercados o pequeños locales el sistema permitirá registrar productos llevar el control
de las fechas de caducidad llamar automáticamente a los productos caducados o próximos a
su caducidad, aplicar descuentos dinámicos preparados previamente por el administrador, la
aplicación además contará con una interfaz que mostrará de forma clara los productos que
están de oferta ayudando tanto a la administración para el manejo de los mismos como a los
usuarios compradores que lo necesiten consultar, el objetivo principal es mejorar la rotación
de la mercancía y disminuir las pérdidas por productos que no se hayan vendido antes de
caducar.

De hecho en el proyecto se consideró la implementación de IA para el desarrollo de
modelos de análisis predictivos aunque en el alcance actual no se plantea la generación
completa de modelos de IA ni de complejos sistemas de Machine Learning, este proyecto
se va a desarrollar principalmente a partir de procesos automáticos simples y reglas lógicas
predefinidas como pueden ser las asociaciones de descuentos en función de la proximidad
de las fechas de caducidad de cada uno de los productos, de este modo el proyecto se
orienta a generar un prototipo funcional y estable que permita verificar la viabilidad
operativa de la propuesta sin depender de las tecnologías avanzadas que agravarían la
complejidad del desarrollo.

El sistema se organiza en dos nodos que se ejecutan en sistemas operativos
distintos y se comunican por red: un servidor FastAPI en Ubuntu (sobre WSL2) y un cliente
de escritorio PyQt6 en Windows. La comunicación usa HTTP con mensajes JSON para las
operaciones y un WebSocket para que el servidor avise de los cambios en tiempo real
(stock, descuentos, productos retirados, cambios de configuración y cierres de sesión).
El servidor es el único que accede a la base de datos (SQLite), aplica las reglas de
negocio, calcula los descuentos y las facturas y comprueba los permisos de cada rol; el
cliente solo muestra información y envía las acciones del usuario. El acceso se controla
con un token firmado (JWT) y la sesión se cierra automáticamente tras un tiempo de
inactividad que el administrador puede configurar. Siguen sin considerarse clústeres,
réplicas, balanceo de carga ni servicios en la nube: hay un único servidor y una única base de
datos, y la demostración corre en una sola máquina física con los dos sistemas operativos
conectados por red real (TCP/IP), de modo que la arquitectura es distribuida en dos
nodos, no un sistema tolerante a fallos. La aplicación contempla dos tipos de usuarios
principales, el administrador o vendedor responsable de la gestión del inventario, los
descuentos, los usuarios y la configuración, y el usuario comprador que podrá ver la lista
de productos en oferta en un instante determinado, comprar y obtener su factura.

Nota de cambio de alcance respecto a la versión original: la versión inicial describía
una aplicación de escritorio única con base de datos local, sin arquitectura distribuida ni
sincronismo en tiempo real. En la versión final se separó el sistema en servidor y cliente
(dos nodos), se añadieron el token con cierre de sesión por inactividad configurable, la
gestión de usuarios, las notificaciones en tiempo real por WebSocket, la factura
guardada en base de datos con IVA y el almacenamiento de contraseñas con argon2id. Se
eliminó el nivel de descuento "Medio 15 %", que nunca tuvo efecto. Quedan fuera de alcance, igual que antes, la
integración con sistemas comerciales reales, los pagos electrónicos reales, la nube y la
inteligencia artificial avanzada.

Hay que señalar que el proyecto no abarca la integración con sistemas comerciales o
plataformas empresariales vigentes en un entorno productivo actualmente utilizado por
grandes supermercados, el alcance del proyecto queda restringido únicamente al desarrollo
de un prototipo académico y funcional que permita validar el comportamiento del sistema
evaluar la aceptación de los usuarios y demostrar la viabilidad de una gestión automatizada
de los descuentos en el contexto de los productos perecederos, por lo tanto aspectos como
la implementación masiva la conexión con sistemas de facturación reales los pagos
electrónicos la infraestructura sobre la nube la inteligencia artificial avanzada queda fuera
del alcance del proyecto y podrían considerarse funcionalidades adicionales en un futuro.


## Diagrama De Gantt

```
Objetivo Actividad
```
```
# Semana Segundo
Corte
1 2 3 4 5 6
```
1. Analizar herramientas y
tecnologías para el desarrollo
del sistema

```
Investigación sobre IA y
descuentos dinámicos x^ x^ x^ x^ x^ x^
Evaluación del entorno y
herramientas
x x x x x x
```
```
Capacitación en tecnologías x x x x x x
```
2. Levantar requerimientos
    del sistema

Estudio de casos similares (^) **x x x x x**
Aplicación de encuestas a
usuarios^
**x x x x x**
Análisis de necesidades (^) **x x x x x**

3. Diseñar la solución del
    sistema

```
Diseño de arquitectura cliente-
servidor^
x x x x
```
Desarrollo del algoritmo IA (^) **x x x x**
Diseño de interfaz gráfica (^) **x x x x**

4. Implementar el sistema

Integración con base de datos (^) **x x x**
Desarrollo completo del sistema (^) **x x x**


Pruebas del sistema (^) **x x x**

5. Evaluar y cerrar el
    proyecto

Testeo final del sistema (^) **x x**
Documentación del proyecto (^) **x x**
Entrega final del proyecto (^) **x x**


## Resumen Del Producto

El objetivo de este proyecto es el desarrollo de un sistema destinado a la mejora y el
control de la gestión del inventario de productos perecederos mediante la aplicación
automática de descuentos en función del tiempo que resta hasta la fecha de caducidad, esta
solución se plantea como el desarrollo de una solución viable a una problemática recurrente
en el sector comercial, el desperdicio alimentario y la consiguiente pérdida de dinero que se
produce en aquellos consumidores que no compran un producto antes de que su fecha de
caducidad llegue, en este sentido Parfitt (2021) sostiene que un gran porcentaje de la
cantidad de alimentos se pierde en las etapas finales de la cadena de suministro es decir en
el punto de venta ya que es cuando se producen la falta de medios de control y decisión. en
esta línea el sistema que se presenta trata de hacer frente a este escenario en base al análisis
de las condiciones de los inventarios y de los descuentos que ayuden a incentivar la compra
del producto de manera que se produzca antes de perder el valor de venta, aunque se
planteó la opción de incorporar inteligencia artificial como un medio de mejora de la
propuesta, el objetivo de este proyecto es el desarrollo de una solución básica que permita
la automatización de las condiciones de los productos próximos a caducar.

El sistema está basado en una arquitectura distribuida de dos nodos con el modelo
cliente servidor, cuyo objetivo es gestionar el inventario y permitir que los usuarios
interactúen con la aplicación desde otro equipo o sistema operativo. El servidor central
(FastAPI, en Ubuntu sobre WSL2) es quien se ocupa de gestionar la información del
sistema y de manejar las operaciones de los productos, descuentos, ventas, facturas y
usuarios; el cliente (PyQt6, en Windows) representa la aplicación de escritorio que usan
los usuarios. Ambos nodos se comunican por HTTP (REST con JSON) y por un WebSocket
para los eventos en tiempo real, y cada usuario se identifica con un token JWT. A diferencia
de sistemas empresariales complejos que emplean varios nodos de procesamiento,
réplicas y balanceo de carga, este proyecto tiene un único servidor y una única base de
datos: es un prototipo académico
orientado a comprobar si realmente la arquitectura cumple con los requerimientos
funcionales del sistema, para Baryannis (2019), sigue siendo una de las arquitecturas más
utilizadas en las aplicaciones de gestión en virtud de su simplicidad, estabilidad y facilidad
de mantenimiento.

El sistema dispone de funcionalidades automatizadas para detectar productos
próximos a su fecha de caducidad y de forma automática, aplicar descuentos dinámicos, se
basará para la automatización en los parámetros básicos del sistema esto es la fecha de
caducidad apuntada en el inventario y el tiempo hasta la venta del producto, no se pretende
en esta etapa del desarrollo de la aplicación un sistema muy sofisticado en cuanto a
inteligencia artificial o de machine learning, no obstante sí que se ha previsto una lógica de
automatización capaz de calcular los descuentos utilizando unas reglas prediseñadas por el
propio administrador, se persigue así optimizar el proceso de control de productos
perecederos y aunando esfuerzos con los empleados del establecimiento disminuir la carga
de trabajo manual, según Dutta (2020), la automatización de los procesos de inventario y
gestión comercial puede contribuir a un incremento significativo de la eficiencia operativa
y a la reducción de las pérdidas debidas a los errores humanos.

Desde el punto de vista de la infraestructura el proyecto se apoya en una base de
datos SQLite que administra únicamente el servidor, de modo que toda la información a
la que hace referencia el proyecto (productos, usuarios, descuentos, ventas, facturas,
sesiones y configuración) está almacenada en el nodo servidor y los clientes no acceden a
ella directamente, solo a través de la API. La decisión de mantener SQLite está
justificada por el alcance académico y funcional del proyecto ya que es
posible simplificar la administración del sistema y reducir los costes de implantación,


asimismo este tipo de estructura contribuye a facilitar el mantenimiento y la prueba del
prototipo en entornos controlados. Se renuncia a la replicación, al balanceo de carga, al
cifrado TLS de las comunicaciones (el tráfico es HTTP, pensado para una red de confianza)
y a los servicios en la nube. A pesar de esto el sistema mantiene una
organización de los datos y una separación en capas que permiten una futura
escalabilidad si así lo requiere, por ejemplo cambiando SQLite por un motor de base de
datos de servidor y añadiendo HTTPS.

La seguridad de la información y la tolerancia a fallos constituyen asimismo un
aspecto importante a tomar en cuenta por parte del diseño de este sistema, para ello se
establece la necesidad de hacer copia de los datos contenidos en el sistema de forma que se
pueda recuperar dicha información en caso de fallos técnicos o de pérdida de información,
el sistema también cuenta con validación de acceso mediante usuario y contraseña
(guardada con argon2id), un token firmado con cierre automático de la sesión por
inactividad y comprobación de permisos por rol en el servidor, de modo que la información
guardada en los sistemas sólo sea objeto de modificación por parte de
usuarios autorizados dentro del inventario, Zhang (2022) concretó que incluso los sistemas
de pequeña escala deberían considerar las medidas de protección y recuperación de la
información como parte del sistema para asegurar la continuidad del proceso de forma que
emerjan informaciones que no se vayan a perder.

Con respecto a la administración del sistema el sistema en particular se aplica a dos
tipos de usuarios, el administrador o vendedor y el usuario comprador, el primero podrá
utilizar las funciones de registrar producto actualizar el inventario consultar los productos
que están en fecha de caducidad y configurar descuentos de forma automática, en lo que
respecta al usuario comprador éste podrá consultar los productos en el carrito y las
informaciones relativas a las promociones para los productos en el programa activo de su
aplicación descontando de este modo la importancia de una estandarización de las
actividades, tal enfoque mucho más simplificado del previsto inicial permite que el sistema
sea utilizado y comprendido sin demasiadas connotaciones para los que están relacionados


con las gestiones comerciales ni para los consumidores que desean simplemente adquirir
productos que se venden a precios algo más económicos que los previstos.

Además, el sistema tiene como objetivo dotarse de beneficios de tipo económico y
de tipo social, en el aspecto económico, la implementación de este permite amortiguar las
pérdidas generadas por los productos que no se venden antes de su fecha de caducidad
optimizando la rotación del inventario y por tanto potenciando las ventas de la tienda, en el
plano social y ambiental ayuda a reducir el desperdicio de los alimentos a través de
prácticas de consumo más responsables, en ese sentido el consumidor también sale
beneficiado porque tiene acceso a productos de calidad a precios reducidos, propiciando así
prácticas de compra más accesibles y sostenibles.

Por su parte la creación de este sistema se plantea como una propuesta tecnológica
simple, pero de utilidad práctica que intenta solucionar una problemática real en el ámbito
del sector comercial, la unión de la automatización de descuentos la gestión del inventario y
la gestión centralizada de los datos en un servidor permitirá la creación de una herramienta simple, eficaz y
escalable destinada a comercios pequeños o a pruebas piloto, aunque el desarrollo del
proyecto no ha incorporado réplicas, balanceo de carga ni tecnologías de
inteligencia artificial potentes en su versión actual y se limita a una arquitectura distribuida de dos nodos, sí sirve como una base para posteriores
mejoras y desarrollos tecnológicos, de esta manera se conjuga el sistema como una
alternativa factible para mejorar la gestión de los productos perecederos y como un medio
para contribuir a la disminución de los residuos alimentarios apoyándose en las
herramientas tecnológicas disponibles.


## Requisitos Y Requerimientos De Usuario

Los requisitos y requerimientos del sistema se dividen en tres categorías principales
que garantizan su correcto funcionamiento y calidad en cuanto a los requisitos funcionales
el sistema debe permitir el registro de productos dentro del inventario realizar una
clasificación automática basada en la proximidad a la fecha de vencimiento aplicar
descuentos dinámicos de manera automática según el análisis de riesgo de cada producto y
ofrecer una visualización clara y actualizada del inventario para facilitar la toma de
decisiones por otro lado los requisitos no funcionales aseguran la calidad del sistema
destacándose la confiabilidad para mantener la integridad de los datos la eficiencia en el
procesamiento de la información la portabilidad para su uso en diferentes entornos
tecnológicos y la mantenibilidad que permite realizar mejoras y actualizaciones de forma
sencilla las restricciones del sistema establecen ciertos límites en su implementación tales
como su uso en entornos controlados durante la fase de desarrollo la dependencia de una
base de datos para el almacenamiento de la información y las limitaciones de hardware que
pueden influir en el rendimiento del sistema.


### Requerimientos Funcionales Del Sistema.....................................................................

```
ID Requerimiento RF- 01
Nombre Autenticación de usuarios
Descripción El sistema debe permitir el ingreso mediante usuario y contraseña,
las credenciales las verifica el servidor contra la base de datos y, si
son correctas, este entrega un token (JWT) que el cliente envía en
cada petición. Solo los usuarios con estado activo podrán iniciar
sesión, el sistema debe validar campos vacíos y mostrar el mismo
mensaje de error ante usuario inexistente, inactivo o contraseña
incorrecta (sin revelar cuál fue la causa). Tras 5 intentos fallidos
de un mismo usuario se bloquea el ingreso durante 60 segundos.
Prioridad Alta
```
```
ID Requerimiento RF- 02
Nombre Control de acceso por roles
Descripción El sistema maneja dos roles: administrador y comprador. Tras
autenticarse, cada rol accede a una interfaz diferente, el
administrador tiene acceso completo al sistema, el comprador solo
puede visualizar los productos que tienen descuento activo, comprar
y consultar sus propias facturas. El permiso de cada operación se
comprueba en el servidor, no solo en la interfaz: una petición de un
comprador a una operación de administrador es rechazada con el
código 403.
Prioridad Alta
```

**ID Requerimiento** RF- 03
**Nombre** Registro de productos
**Descripción** Permitir al administrador registrar nuevos productos con: nombre,
categoría, precio base, stock actual, stock máximo y fecha de
vencimiento, almacenamiento con estado activo.
**Prioridad** Alta

**ID Requerimiento** RF- 04
**Nombre** Edición de productos
**Descripción** Modificación de cualquier campo de un producto existente
seleccionándolo desde la tabla de inventario.
**Prioridad** Media

**ID Requerimiento** RF- 05
**Nombre** Eliminación de productos
**Descripción** Eliminación lógica: el producto se marca como inactivo (no se
borra físicamente) y deja de ser visible en las vistas generales
**Prioridad** Media


**ID Requerimiento** RF- 06
**Nombre** Visualización del inventario
**Descripción** Tabla detallada con ID, nombre, categoría, precios, stocks y fecha
de vencimiento
**Prioridad** Alta

**ID Requerimiento** RF- 07
**Nombre** Exportación de reportes
**Descripción** Exportar inventario a Excel (.xlsx) o PDF con marca de tiempo
automática en el nombre del archivo.
**Prioridad** Media

**ID Requerimiento** RF- 08
**Nombre** Evaluación automática de riesgo
**Descripción** Cálculo automático basado en:

- Crítico: Vencido o ≤ 3 días.
- Alto: ≤ 7 días.
- Medio: Sobrestock (≥ 90% máx) o Stock bajo (≤ 10 und, con stock mayor
  que cero; es solo una alerta y no genera descuento).
- Normal: Sin condiciones.
Un producto vencido se clasifica como Crítico pero no se vende ni
recibe descuento: se retira del inventario (RF-22). El cálculo lo
realiza el servidor (server/domain/riesgo.py) con umbrales tomados de
la configuración.
**Prioridad** Alta


**ID Requerimiento** RF- 09
**Nombre** Aplicación automática de descuentos
**Descripción** Generación de descuentos según riesgo: Crítico (50%), Alto
(30%) y Sobrestock (10%). El stock bajo solo genera una alerta, sin
descuento. El nivel "Medio 15%" de la versión original se eliminó
porque nunca tuvo efecto. Si un producto cumple varias condiciones
se aplica el mayor descuento. Los porcentajes son configurables
(RF-13). El servidor recalcula los descuentos automáticamente
cada 60 segundos (intervalo configurable) y los guarda en la base
de datos; el precio que ve el comprador y el que se cobra
proceden de la misma evaluación.
**Prioridad** Alta

**ID Requerimiento** RF- 10
**Nombre** Dashboard de riesgo
**Descripción** Panel resumen con conteos por nivel de riesgo y lista de productos
que requieren atención inmediata (motivo, descuento, precios).
**Prioridad** Alta

**ID Requerimiento** RF- 11
**Nombre** Vista de alertas
**Descripción** Interfaz dedicada para productos problemáticos agrupados por
severidad.
**Prioridad** Media

**ID Requerimiento** RF- 12
**Nombre** Visualización de descuentos (Comprador)
**Descripción** Acceso exclusivo a productos con descuento activo. Información:
nombre, categoría, stock, precio original, precio final y %.
La lista se actualiza al instante cuando el servidor avisa de un
cambio por WebSocket (RF-25) y, si la conexión en tiempo real
se pierde, se consulta cada 60 s.
**Prioridad** Alta

**ID Requerimiento** RF- 13
**Nombre** Configuración del sistema
**Descripción** Ajuste de parámetros por el administrador: datos de empresa
(NIT, nombre, dirección, teléfono), moneda, IVA, decimales de la
moneda, umbrales de alerta, porcentajes de descuento (crítico,
alto y sobrestock), intervalo de escaneo y parámetros de sesión:
inactividad_segundos (tiempo sin actividad antes de cerrar la
sesión) y aviso_segundos (segundos de aviso previo). Los valores
se validan por rango en el servidor y se guardan en la tabla
configuracion de la base de datos, por lo que persisten al
reiniciar el servidor.
**Prioridad** Media


**ID Requerimiento** RF- 14
**Nombre** Cierre de sesión
**Descripción** Cualquier usuario puede cerrar sesión desde su interfaz, el sistema
revoca la sesión en el servidor (el token deja de ser válido) y regresa a la
pantalla de login para permitir el ingreso con otra cuenta. La
sesión también se cierra automáticamente por inactividad (RF-24).
**Prioridad** Media

**ID Requerimiento** RF- 15
**Nombre** Carrito de compras
**Descripción** El comprador puede agregar productos en oferta a un carrito desde
la vista principal. Cada producto muestra un botón "Agregar al
carrito" que se deshabilita automáticamente si el stock disponible
es cero, el sistema impide agregar más unidades de las que hay en
stock y muestra un aviso si se intenta superar ese límite.
**Prioridad** Alta


**ID Requerimiento** RF- 16
**Nombre** Gestión de cantidades en el carrito
**Descripción** El comprador puede aumentar o disminuir la cantidad de cada
producto dentro del carrito usando los controles + y −, si la
cantidad llega a cero, el producto se elimina del carrito
automáticamente ademas puede eliminar un producto
individualmente con el botón × o vaciar el carrito completo con
confirmación previa
**Prioridad** Alta

**ID Requerimiento** RF- 17
**Nombre** Resumen del carrito en tiempo real
**Descripción** El panel del carrito muestra en todo momento el subtotal sin
descuento, el ahorro total generado por los descuentos y el total a
pagar antes de IVA (el IVA se suma al confirmar el pago, si está
configurado). Estos valores se recalculan automáticamente cada vez que el
comprador modifica cantidades o elimina productos. Los montos son
pesos enteros.
**Prioridad** Alta


**ID Requerimiento** RF- 18
**Nombre** Proceso de pago (datos del cliente y método de pago)
**Descripción** Al iniciar el proceso de pago, el sistema muestra un diálogo con la
tabla de productos seleccionados, los totales, los datos del
cliente (nombre y documento, obligatorios) y una sección de
pago. El método de pago puede ser efectivo o tarjeta simulada (no
se piden ni se guardan números de tarjeta). En efectivo, el comprador
ingresa el monto recibido y el sistema calcula el cambio en tiempo
real. El botón de confirmar permanece deshabilitado mientras el
monto ingresado sea menor al total a pagar. Si el monto es
insuficiente, se muestra el valor exacto que falta (y el servidor
rechaza la compra con el código EFECTIVO_INSUFICIENTE). El IVA se calcula sobre el
precio ya con descuento: total = precio con descuento + IVA. Todos los
montos son pesos enteros, con redondeo de la mitad hacia arriba.
**Prioridad** Alta

**ID Requerimiento** RF- 19
**Nombre** Registro de ventas
**Descripción** Al confirmar el pago, el servidor registra la compra como una
factura (tabla facturas, con número consecutivo FAC-nnnnnn, cliente,
método de pago, subtotal, ahorro, IVA, total, efectivo y cambio) y una línea
de detalle por producto (tabla detalle_factura) con la cantidad,
precio unitario, porcentaje de descuento, precio final y subtotal.
Simultáneamente, descuenta del stock de cada producto la
cantidad comprada. Todo ocurre en una sola transacción y con descuento
de stock condicionado (stock mayor o igual a la cantidad): si algún
producto no tiene stock suficiente, está vencido o inactivo, la compra
completa se revierte y no se consume número de factura. Dos
compradores que pidan la última unidad a la vez nunca provocan
sobreventa: uno compra y el otro recibe el error STOCK_INSUFICIENTE.
**Prioridad** Alta


**ID Requerimiento** RF- 20
**Nombre** Vista previa de factura dentro de la aplicación
**Descripción** Después de confirmar el pago, el sistema muestra la factura
completa dentro de la aplicación sin cerrar ninguna ventana., la
factura incluye: número único de factura, fecha y hora, datos del
negocio, información del cliente (nombre y documento), tabla de productos con precios y
descuentos, resumen de totales con ahorro destacado en verde, el IVA
(calculado sobre el precio con descuento), el método de pago y, en
efectivo, el efectivo recibido y el cambio entregado. Los datos de la
factura los entrega el servidor (la misma factura guardada en la base
de datos) y el cliente solo los muestra. Los montos son pesos enteros.
**Prioridad** Media

**ID Requerimiento** RF- 21
**Nombre** Generación y apertura del PDF de factura
**Descripción** La factura se guarda como PDF únicamente cuando el comprador
pulsa el botón "Guardar / Imprimir PDF", el archivo se genera en el
equipo cliente (con ReportLab, a partir de los datos de la factura que
entrega el servidor) en la carpeta de reportes del usuario con el
número de factura como nombre; una vez guardado, el sistema abre el PDF
automáticamente con el visor predeterminado del sistema
operativo.
**Prioridad** Media


**ID Requerimiento** RF- 22
**Nombre** Eliminación automática de productos vencidos
**Descripción** El servidor verifica en cada escaneo automático (cada 60 segundos,
intervalo configurable) si existen productos cuya fecha y hora de vencimiento ya
expiró. Los productos vencidos son desactivados automáticamente del
inventario sin necesidad de intervención manual (baja lógica) y no se
pueden vender mientras tanto: la compra de un producto vencido se rechaza
aunque el escaneo aún no lo haya retirado. El administrador
recibe una notificación con el listado exacto de productos retirados
(evento productos_retirados por WebSocket) y las vistas se actualizan de
inmediato para reflejar los cambios; los demás usuarios ven que el
producto desaparece del catálogo.
**Prioridad** Alta


**ID Requerimiento** RF- 23
**Nombre** Gestión de usuarios (nuevo)
**Descripción** El administrador puede listar, crear y modificar usuarios desde la
vista Usuarios: nombre, usuario, rol (administrador o comprador), estado
activo/inactivo y contraseña (mínimo 8 caracteres, guardada con
argon2id; nunca se devuelve el hash). No se permiten nombres de usuario
duplicados. Desactivar un usuario, o cambiar su contraseña o su rol, cierra
de inmediato sus sesiones abiertas. Un administrador no puede desactivarse
ni cambiar su propio rol, para no quedarse sin acceso. Las credenciales
iniciales (admin y comprador) se generan en el primer arranque y no están
escritas en el código.
**Prioridad** Alta

**ID Requerimiento** RF- 24
**Nombre** Cierre de sesión por inactividad configurable (nuevo)
**Descripción** La sesión de cualquier usuario se cierra automáticamente tras un
tiempo sin actividad. Por defecto son 180 segundos con un aviso 30 segundos antes
del cierre, con cuenta regresiva y botón "Seguir conectado"; el administrador puede cambiar
ambos valores en Configuración (inactividad de 30 a 3600 s, aviso menor que la
inactividad) y el cambio se aplica también a las sesiones ya abiertas. Solo cuenta
como actividad el uso real del teclado y el ratón (o cambiar de vista): el refresco
automático y los eventos del WebSocket no la renuevan. El cliente cierra
la sesión con su propio temporizador y el servidor la caduca por su lado, de modo
que un token inactivo deja de ser válido aunque el cliente no lo informe. Además, cada
token tiene una vigencia máxima absoluta (por defecto 480 minutos).
**Prioridad** Alta

**ID Requerimiento** RF- 25
**Nombre** Notificaciones en tiempo real por WebSocket con respaldo de sondeo (nuevo)
**Descripción** El servidor notifica a los clientes conectados los eventos
stock_actualizado, descuento_cambiado, productos_retirados (solo
administrador), config_cambiada y sesion_cerrada, de modo que las vistas
(catálogo, inventario, alertas, dashboard) se refrescan sin que el usuario haga
nada. Si la conexión se pierde, el cliente reconecta con espera creciente y mientras tanto
consulta los datos cada 60 segundos; al reconectar hace una consulta de
resincronización. La barra de estado indica si el servidor está en línea, el sistema
operativo del servidor y si hay eventos en vivo.
**Prioridad** Alta

### Requerimientos No Funcionales Del Sistema

```
ID Requerimiento RNF- 01
Nombre Seguridad de credenciales
Descripción Las contraseñas de todos los usuarios del sistema se almacenan
en la base de datos del servidor solo como hash argon2id; en ningún
momento se guarda la contraseña en texto plano ni se devuelve en
las respuestas. Los hashes SHA-256 de la versión anterior se
reemplazan por argon2id de forma transparente en el primer ingreso
correcto. El sistema no permite el acceso a ninguna operación sin un token
válido (firmado, no expirado y con sesión vigente), y la autorización
de cada rol se comprueba en el servidor. Las respuestas de error no
revelan si el usuario existe. Nota: la contraseña viaja por HTTP sin
TLS entre los nodos, por lo que el sistema está pensado para una red
de confianza (en producción iría detrás de HTTPS).
Prioridad Alta
```

**ID Requerimiento** RNF- 02
**Nombre** Rendimiento del escaneo automático
**Descripción** El motor de riesgo debe completar el análisis completo del
inventario y la detección de productos vencidos en un tiempo no
perceptible para el usuario. El ciclo de escaneo automático se
ejecuta en el servidor cada 60 segundos (configurable) en un hilo de
segundo plano, de modo que no depende de que haya clientes abiertos. En el cliente,
todas las llamadas a la red se hacen en hilos de trabajo (QThreadPool) y los
resultados vuelven al hilo gráfico, así que la interfaz no se bloquea
ni siquiera cuando el servidor está caído (prueba E2E: el mayor hueco del
hilo gráfico fue de 83 ms).
**Prioridad** Alta
**ID Requerimiento** RNF- 03
**Nombre** Persistencia y consistencia de los datos
**Descripción** Toda la información del sistema, incluyendo productos, usuarios,
facturas con su detalle, descuentos, sesiones y configuración, se almacena en una base
de datos SQLite que administra únicamente el servidor y que se inicializa
automáticamente al arrancar (modo WAL, claves foráneas y restricciones CHECK
activas). Las operaciones de escritura que involucren múltiples registros,
como el registro de una compra con descuento de stock, se
ejecutan dentro de una transacción, garantizando que ante
cualquier error ningún cambio parcial quede guardado. Los datos
(incluida la configuración) sobreviven al reinicio del servidor.
**Prioridad** Alta


**ID Requerimiento** RNF- 04
**Nombre** Usabilidad y retroalimentación al usuario
**Descripción** Toda acción que modifique datos, como eliminar un producto,
vaciar el carrito o confirmar una compra, debe solicitar
confirmación explícita al usuario antes de ejecutarse, el sistema
debe mostrar mensajes de error descriptivos cuando una operación
falla y mensajes de éxito cuando se completa correctamente, los
botones que no están disponibles en un contexto determinado
deben deshabilitarse visualmente para evitar acciones inválidas.
**Prioridad** Alta

**ID Requerimiento** RNF- 05
**Nombre** Portabilidad del sistema
**Descripción** Cada nodo debe poder ejecutarse en sistemas operativos
distintos sin modificar el código. La portabilidad se demostró con dos
sistemas operativos a la vez: el servidor en Ubuntu 26.04 (WSL2) y el cliente en
Windows 11, comunicados por HTTP y WebSocket (`GET /health` devuelve el sistema
del servidor, "Linux"). Las rutas
de almacenamiento de la base de datos, los reportes y los archivos
de log se determinan automáticamente en tiempo de ejecución
(variables de entorno o los directorios estándar de cada plataforma, con
platformdirs). Solo se probó la combinación Ubuntu (servidor) y Windows
(cliente); no se verificaron el servidor en Windows ni el cliente en Linux o macOS.
**Prioridad** Alta

**ID Requerimiento** RNF- 06
**Nombre** Arquitectura distribuida y en capas (nuevo)
**Descripción** El sistema se compone de dos nodos independientes que solo se
comunican por red: el servidor (Ubuntu/WSL2) es el único dueño de la base
de datos, de las reglas de negocio y de la autorización; el cliente (Windows)
no importa código del servidor ni abre la base de datos y accede únicamente a
través de la API REST y el WebSocket, cuyo contrato único son los modelos
Pydantic de shared/. Cada nodo instala solo sus dependencias
(requirements-server.txt y requirements-client.txt). El servidor se divide en
capas: api (rutas FastAPI y WebSocket), application (casos de uso y
transacciones), domain (reglas puras sin frameworks), infrastructure (SQLAlchemy y
repositorios) y security (argon2id, JWT y sesiones). Limitaciones asumidas: un
solo servidor, un solo proceso (el limitador de intentos y el bus de eventos viven
en memoria), sin réplicas, sin balanceo y sin TLS.
**Prioridad** Alta

**ID Requerimiento** RNF- 07
**Nombre** Observabilidad y registros sin datos sensibles (nuevo)
**Descripción** El servidor y el cliente escriben registros (logs) con fecha,
nivel y módulo; el servidor los guarda en un archivo rotativo (2 MB, 3
copias) además de la consola. Los registros no deben contener credenciales:
un filtro reemplaza `token=<JWT>` por `token=***` (el WebSocket se
autentica con el token en la URL y uvicorn la registraría completa), y no se
registran contraseñas. Los errores no controlados devuelven un mensaje
genérico (ERROR_INTERNO) sin detalles internos. Excepción: las credenciales
iniciales generadas en el primer arranque se muestran una sola vez y se guardan
en un archivo de acceso restringido. El servicio expone `GET /health` (estado,
versión y sistema operativo) para comprobar que está en línea.
**Prioridad** Media


## Interfaz Gráfica, Maquetación

### Interfaz: Login

#### Tipografía

```
Elemento de UI Fuente Tamaño Peso Color
Título 'Inventario App' Segoe UI 20px 700 — Bold #111827
Subtítulo 'Gestión de
descuentos dinámicos'
Segoe UI 13px 400 — Normal #6B7280
```
```
Etiquetas de campo
(Usuario, Contraseña)
Segoe UI 12px
```
##### 600 —

```
Semibold
```
##### #374151

```
Texto de inputs Segoe UI 13px 400 — Normal #111827
```

```
Botón 'Iniciar sesión' Segoe UI 13px
```
##### 600 —

```
Semibold
```
##### #FFFFFF

```
Mensaje de error Segoe UI 12px 400 — Normal #DC2626
Versión (pie de ventana) Segoe UI 11px 400 — Normal #9CA3AF
```
#### Paleta de colores

```
Color HEX Uso en esta pantalla
#FFFFFF Fondo de la ventana y del formulario
```
```
#2563EB
Barra de acento superior, borde activo de inputs, botón 'Iniciar
sesión'
#1D4ED8 Hover del botón 'Iniciar sesión'
#1E40AF Fondo presionado del botón 'Iniciar sesión'
#111827 Título 'Inventario App' y texto de inputs
#6B7280 Subtítulo 'Gestión de descuentos dinámicos'
#374151 Etiquetas de campo (Usuario, Contraseña)
#F9FAFB Fondo de los campos de texto
#D1D5DB Borde inactivo de los campos de texto
#DC2626 Mensaje de error
#9CA3AF Texto de versión en el pie de la ventana
```

### Interfaz: Dashboard, Principal Administrador

#### Tipografía

```
Elemento de UI Fuente Tamaño Peso
```
```
Título 'Dashboard' Segoe UI 20px 700 — Bold
Subtítulo 'Productos que
requieren atención'
Segoe UI 13px 600 — Semibold
```
```
Etiqueta de tarjeta de resumen Segoe UI 12px 600 — Semibold
Número grande (Total) Segoe UI 30px 700 — Bold
```

```
Número grande (Críticos) Segoe UI 30px 700 — Bold
Número grande (Riesgo Alto) Segoe UI 30px 700 — Bold
Número grande (Riesgo Medio) Segoe UI 30px 700 — Bold
Nombre del producto en fila Segoe UI 13px 700 — Bold
Motivo de alerta Segoe UI 11px 400 — Normal
Badge de nivel
(Crítico/Alto/Medio)
Segoe UI 11px 700 — Bold
```
```
Badge de descuento Segoe UI 12px 700 — Bold
Precio original tachado Segoe UI 11px 400 — Normal
Precio sugerido Segoe UI 13px 700 — Bold
```
#### Paleta de colores

```
Color HEX Uso en esta pantalla
#F9FAFB Fondo general de la vista
#111827 Título 'Dashboard'
#6B7280 Subtítulo y etiquetas de tarjetas de resumen
#FFFFFF Fondo de tarjetas de resumen y filas de productos
#E5E7EB Borde de tarjetas y filas
```

#374151 Número grande en tarjeta Total

#DC2626 Número grande en tarjeta Críticos y texto badge Crítico

#D97706 Número grande en tarjeta Riesgo Alto y texto badge Alto

#CA8A04 Número grande en tarjeta Riesgo Medio y texto badge Medio

#FEE2E2 Fondo badge nivel Crítico

#FEF3C7 Fondo badge nivel Alto

#FEF9C3 Fondo badge nivel Medio

#9CA3AF Texto del motivo de alerta y precio original tachado

#1D4ED8 Texto del badge de descuento

#EFF6FF Fondo del badge de descuento

#15803D Precio sugerido con descuento

#166534 Texto del mensaje 'sin alertas'

#F0FDF4 Fondo del mensaje 'sin alertas'

#BBF7D0 Borde del mensaje 'sin alertas'


### Interfaz: Principal Cliente

#### Tipografía

```
Elemento de UI Fuente Tamaño Peso
Texto 'Inventario App' (barra
superior)
Segoe UI 15px 700 — Bold
```
```
Texto 'Hola, Nombre' Segoe UI 12px 400 — Normal
Botón cerrar sesión Segoe UI 12px 600 — Semibold
Título 'Productos en oferta' Segoe UI 17px 700 — Bold
Contador de productos Segoe UI 12px 400 — Normal
```

Nombre del producto Segoe UI 14px 700 — Bold

Categoría y stock Segoe UI 12px 400 — Normal

Motivo Segoe UI 11px 400 — Normal

Badge de descuento Segoe UI 11px 700 — Bold

Precio original tachado Segoe UI 11px 400 — Normal

Precio con descuento Segoe UI 14px 700 — Bold

Botón 'Agregar al carrito' Segoe UI 12px 600 — Semibold

Título 'Carrito' Segoe UI 15px 700 — Bold

Nombre en fila del carrito Segoe UI 12px 600 — Semibold

Subtotal por fila y cantidad Segoe UI
12px–
13px

##### 600 – 700 —

```
Semibold/Bold
```
Etiqueta Subtotal / Ahorro Segoe UI 12px 400 — Normal

Valor Ahorro Segoe UI 12px 700 — Bold

Etiqueta Total Segoe UI 14px 700 — Bold

Valor Total Segoe UI 16px 700 — Bold

Botón 'Ir al pago' Segoe UI 14px 700 — Bold

Botón 'Vaciar carrito' Segoe UI 12px 600 — Semibold


#### Paleta de colores

```
Color HEX Uso en esta pantalla
#F9FAFB Fondo general de la vista
#FFFFFF Barra superior, panel del carrito y fondo de tarjetas
#E5E7EB Borde inferior de la barra superior y borde izquierdo del carrito
#1E40AF Texto 'Inventario App' y valor total a pagar en el carrito
#6B7280 Texto 'Hola, Nombre', contador de productos y texto de soporte
#F3F4F6 Fondo del botón cerrar sesión
#374151 Texto del botón cerrar sesión
#D1D5DB Borde del botón cerrar sesión y botones +/−
#111827 Título 'Productos en oferta', nombre de producto y cantidad
#9CA3AF Motivo y precio original tachado
#DC2626 Borde izquierdo y acento nivel Crítico
#FEE2E2 Fondo badge nivel Crítico
#D97706 Borde izquierdo y acento nivel Alto
#FEF3C7 Fondo badge nivel Alto
#CA8A04 Borde izquierdo y acento nivel Medio
```

#FEF9C3 Fondo badge nivel Medio

#15803D Precio con descuento en tarjetas de producto

#2563EB Botón 'Agregar al carrito'

#16A34A Valor del ahorro en el resumen del carrito

#FEF2F2 Fondo hover del botón × para eliminar ítem del carrito


### Interfaz: Facturas

#### Tipografía

```
Elemento de UI Fuente Tamaño Peso
Número de factura (barra de
herramientas)
Segoe UI 14px 700 — Bold
```
```
Botón 'Guardar / Imprimir PDF' Segoe UI 12px 700 — Bold
```

Botón 'Cerrar' Segoe UI 12px 400 — Normal

Nombre del negocio Segoe UI 22px 700 — Bold

Texto 'Factura de Venta' Segoe UI 13px 400 — Normal

Etiquetas de datos (No., Fecha,
Cliente...) Segoe UI^ 12px^400 —^ Normal^

Valores de datos Segoe UI 12px 700 — Bold

Encabezado de tabla Segoe UI 13px 600 — Semibold

Filas de tabla Segoe UI 13px 400 — Normal

Columna descuento Segoe UI 13px 700 — Bold

Subtotal sin descuento Segoe UI 13px 400 — Normal

Ahorro total Segoe UI 13px 700 — Bold

Etiqueta TOTAL A PAGAR Segoe UI 15px 700 — Bold

Valor TOTAL A PAGAR Segoe UI 18px 700 — Bold

Título caja pago recibido Segoe UI 11px 700 — Bold

Efectivo recibido y cambio Segoe UI 12px 700 — Bold

Pie de página Segoe UI 11px 400 — Normal

'Gracias por su compra' Segoe UI 14px 700 — Bold


#### Paleta de colores

```
Color HEX Uso en esta pantalla
#F9FAFB Fondo general de la ventana y filas alternas de tabla
#FFFFFF Barra de herramientas y fondo del documento de factura
```
```
#E5E7EB
Borde inferior de la barra de herramientas y borde del
documento
```
```
#1E40AF Número de factura, nombre del negocio, encabezado de tabla y
valor total
#2563EB Botón 'Guardar / Imprimir PDF'
#374151 Botón 'Cerrar', celdas de tabla y 'Gracias por su compra'
#D1D5DB Borde del botón 'Cerrar'
```
```
#6B7280 Texto 'Factura de Venta', etiquetas de datos y subtotal sin
descuento
#111827 Valores de datos y etiqueta TOTAL A PAGAR
#DC2626 Columna de descuento en la tabla (texto bold)
#16A34A Ahorro total y valor del cambio entregado
#F0FDF4 Fondo de caja 'Pago recibido'
#BBF7D0 Borde de caja 'Pago recibido'
```

#166534 Título de la caja de pago recibido

#9CA3AF Pie de página de la factura


## Estudio De Mercado

En el análisis de mercado para el diseño del sistema inteligente de descuentos
dinámicos para productos perecederos es necesario realizar una revisión de la manera de
adquirir por parte del consumidor actual así como de las emergentes tendencias que están
teniendo lugar en el sector del comercio hoy en día el consumidor presenta un perfil que
tiende a ser más racional a la hora de adquirir productos y se prioriza otra serie de sus
necesidades como la posibilidad de ahorrar que los productos adquiridos sean sostenibles o
bien que su adquisición se pueda traducir en una disminución del desperdicio el cambio de
comportamiento viene determinado por variables de tipo económico social sobre todo en
aquellos contextos donde el coste de los productos ha aumentado y el consumidor toma
conciencia del hecho de que el daño a la naturaleza es cada vez mayor según Dutta (2020),
los consumidores del futuro parecieran valorar cada vez más las alternativas de recursos de
tipo tecnológico que pueden ayudarle a optimizar recursos y a tomar decisiones de manera
informada a tiempo real la propuesta del sistema hace alusión en su propio diseño a estas
demandas del comportamiento del consumidor escogiendo aquellos productos en función
de sus descuentos dinámicos basados en la proximidad a su fecha de caducidad.

Los resultados de la encuesta realizada refuerzan tal tendencia es evidente que una
gran parte de los consumidores estaría dispuesta a comprar productos que hoy por hoy
tienen las fechas de caducidad muy próximas siempre que arrastren una reducción
importante de precios también parece que el ahorro es un factor clave en la decisión de
compra y esto hace que este tipo de productos se conviertan en una práctica alternativa
altamente atractiva para el mercado según Parfitt (2021), la reducción del desperdicio de
alimentos no está ligada sólo a la gestión de la cadena de suministro sino que también


podemos determinar que hay un papel fundamental que juegan los propios consumidores
finales en la valoración de los productos que sí son aptos para el consumo en suma el
sistema no sólo responde a una necesidad económica sino que también ayuda a generar
prácticas de sostenible de momento que se toma conciencia en este sentido del problema
económico y de necesidad que da lugar a un producto útil.

En relación con las actuales exigencias del mercado se puede destacar que la
necesidad de digitalización de los procesos comerciales en torno a la gestión de inventarios
está en auge hay que tener en cuenta que muchos supermercados y tiendas de cadena
todavía utilizan métodos tradicionales o herramientas simples para el control de sus
productos y por lo tanto tienen grandes limitaciones para poder reaccionar ante situaciones
críticas por ejemplo la proximidad de una fecha de caducidad en palabras de Baryannis
(2019), la incorporación de tecnologías avanzadas como la inteligencia artificial ofrece la
posibilidad de llegar a aumentar significativamente la eficiencia de la gestión de inventarios
al proporcionar análisis predictivos y la automatización de procesos, en este sentido, el
sistema propuesto se perfila como una solución innovadora y como respuesta a esta
necesidad existente de modernización.

A nivel proyectado la expectativa del crecimiento de este tipo de soluciones sigue
siendo un hecho, sobre todo en el contexto de la transformación digital y la optimización de
los recursos de las empresas, la adopción de la inteligencia artificial dentro de los procesos
comerciales no solo implica mejores resultados operativos, sino que las empresas también
encuentran beneficios competitivos en un entorno cada vez más demandante y exigente.
Según Kamble (2021) la adopción de tecnologías propias de la Industria 4.0 es clave para el


avance de las empresas hacia abordajes más sostenibles y eficientes por ello el proyecto
tiene un gran potencial de crecimiento y adopción en el medio y largo plazo.

Cabe mencionar con relación a la competencia en la gestión de inventarios que, en
estos momentos, existen diferentes soluciones para la gestión de inventarios, pero éstas sólo
aportan funcionalidades muy básicas como el registro y el control de productos y no
permiten incorporar análisis avanzado y automatización, herramientas como las hojas de
cálculo o los sistemas tradicionales no permiten llevar a cabo análisis predictivos y
tampoco aplicar estrategias de precios dinámicas, por lo que se puede observar que estas
soluciones son inferiores a otras más avanzadas, Zhang (2022) afirma que la toma de
decisiones en el contexto de las empresas apoyándose en inteligencia artificial permite
mejorar la precisión y la rapidez en la gestión de los procesos lo que se traduce en una
mayor eficiencia operativa.

El sistema que se propone es distinto de la competencia gracias a la integración de
inteligencia artificial para la generación automática de descuentos, lo que resulta en una
oferta más completa y eficiente, además, su orientación a la reducción del desperdicio de
alimentos lo convierte en una propuesta coherente con la propuesta comercial actual en la
cual la sostenibilidad es un tema clave efecto proyectado este último va a cambiar con la
incorporación de tecnología por parte de la competencia lo que hace necesaria la
permanencia de un enfoque de continuo cambio del sistema para mantener la ventaja
competitiva.

Con respecto a las ofertas del mercado puede observarse que en la actualidad los
descuentos a los productos que están a punto de vencerse todavía son realizados
manualmente o se trata de las políticas de descuento generales lo cual limita la eficacia del


descuento, el sistema propuesto se basa en un enfoque dinámico y automatizado donde los
descuentos se determinan mediante variables tales como el tiempo que queda hasta el
vencimiento o la demanda del producto de modo que se maximiza la probabilidad de venta
y se optimizan la facturación y la gestión del inventario, según Dutta (2020) la
personalización de las tácticas comerciales mediante datos es una de las tendencias más
importantes en el mercado de hoy lo que corrobora la pertinencia del sistema que se
desarrolla.

Con relación a la comercialización de la propuesta, se plantea una propuesta en la
que se ofrezca como software como un servicio SaaS el que permitirá que los
supermercados puedan acceder a través de subscripciones periódicas, este modelo ofrece
ventajas como la reducción de costes de introducción la posibilidad de una fácil
introducción de este software o la introducción de actualizaciones de manera muy
continuada, también hay que tener en cuenta que podemos comercializarlo añadiendo
servicios como el soporte técnico, capacitaciones a los usuarios que vayan a usarlo o la
posibilidad de que los supermercados lo utilicen con las prestaciones que el cliente
requiera, según Baryannis (2019), los modelos de negocio basados en servicios digitales
son muy recomendables para permitir una alta adopción de tecnologías innovadoras en
sectores comerciales.

La estrategia de comercialización también incluye la puesta en marcha de pruebas
piloto en algunos supermercados locales para poder verificar que el sistema funciona al
tiempo que se justifica la validez de la metodología y se obtiene evidencia de un impacto
positivo la estrategia comercial nos ayudará a conseguir que nuestros nuevos clientes se
convenzan de los beneficios de nuestro sistema al ver cómo se produce una disminución de


las pérdidas junto con mejoras de nuestros procedimientos, de igual forma, también se
pueden llegar a crear alianzas con empresas alimentarias para mejorar la visibilidad del
producto y su posicionamiento.

Respecto al comportamiento del consumidor que hemos mencionado anteriormente,
vale la pena profundizarlo más mediante el estudio de la percepción de calidad la confianza
y el riesgo de adquirir productos próximos a su caducidad a pesar de que, en términos
generales, existe una predisposición a la compra de estos productos, existen aún
consumidores algo reticentes a la adquisición debido a la ausencia de información en
algunas ocasiones o incluso por desconfianza en cuanto al estado del alimento, el sistema
que presentamos puede ayudar de forma notable al ir ofreciendo, bien información
disponible bien actualizada de los productos, lo cual debería generar confianza al
consumidor, en este sentido, Zhang (2022) afirma que la transparencia de estos sistemas
inteligentes influye directamente en la aceptación de estas tecnologías por parte de sus
usuarios.

Por otro lado, el análisis de mercado también tiene que contemplar el efecto
económico que este tipo de soluciones puede generar en los establecimientos comerciales,
en efecto, implementar un sistema automatizado de descuentos hace posible reducir las
pérdidas como consecuencia de productos que no se han vendido y, por tanto, esto se
traduce en un aumento de la rentabilidad del negocio, pero no solo eso, dado que aumenta
la rotación de productos, se optimiza su uso y se reduce la necesidad de reposición, según
Kamble (2021), la optimización de procesos por medio de tecnologías inteligentes permite
además de aumentar el rendimiento óptimo de los procesos operativos, generar ventajas
económicas sostenibles en el tiempo.


Con respecto a la evolución del mercado hay que destacar que la digitalización en el
retail ha ido avanzando en los últimos años, las tecnologías de análisis la inteligencia
artificial y la automatización han permitido a las empresas implementar sus procesos y
adaptarse a las nuevas exigencias del consumidor en este sentido el sistema propuesto en
este trabajo sigue estas líneas de investigación y presenta una solución que combina
diferentes tecnologías para dar respuesta a un problema concreto, Dutta (2020) indica que
las empresas que se adaptan a las tecnologías emergentes tienen una mayor capacidad de
adaptación y respuesta ante cambios en el mercado.

Del mismo modo, la evaluación de la competencia anticipada permite, conocer un
futuro en el que empresas rivales desarrollen determinadas soluciones similares lo que nos
lleva a la necesidad inevitable de que el sistema propuesto esté en continuo proceso de
mejora, incluyendo funcionalidades y optimizaciones fundamentales para su diferenciación
en el mercado y entre estas mejoras se encuentran integraciones con sistemas de
facturación, algoritmos de análisis predictivos más complejos e interfaces de usuario más
intuitivas, Baryannis (2019) también establece que la innovación continua es parte esencial
de la sostenibilidad de soluciones tecnológicas.

Con respecto a la estrategia de comercialización, se puede considerar también una
forma de segmentación del mercado como parte fundamental en la que debería entrar la
oferta del producto el sistema se puede adaptar a diversos tipos de negocio, desde pequeños
supermercados hasta grandes cadenas de distribución, o algo intermedio lo que introduciría
mucha más potencialidad, este tipo de segmentación conlleva a poder ofrecer soluciones a
la medida de los clientes, aumentando así las posibilidades de implementación del sistema.


También se considera interesante tener en cuenta otro aspecto vigente en la
comercialización poder agregar valor en el marco de la incorporación de otras tecnologías,
por ejemplo, el sistema podría estar complementado con aplicaciones de móvil de forma
que el consumidor, consultando su aplicación de móvil, pueda conocer tiempo real qué
productos están disponibles en el establecimiento y en qué momento.

Esta integración constituye una mejora de la experiencia de usuario y mejora la
visibilidad de los productos, dado que, tal y como afirman Parfitt (2021) la conexión entre
los sistemas tecnológicos y el consumidor final es lo que permite maximizar el impacto de
soluciones orientadas a la reducción del desperdicio, finalmente a largo plazo el sistema
tiende a convertirse en una referencia más generalizada: Kamble (2021) afirma que para
mantener la sostenibilidad tecnológica, es esencial seguir innovando, por lo tanto, el
proyecto responde no solo a una necesidad sino que también se proyecta como un recurso
estratégico para el futuro del sector comercial.


## Modelo de negocio

El modelo de negocio se fundamentará en la venta del software a través de la
comercialización del software a bibliotecas mediante la mensualidad de suscripción a
aquellas tiendas de alimentación y supermercados que deseen utilizar la plataforma,
también se pueden ofrecer servicios complementarios como por ejemplo soporte técnico,
mantenimiento del sistema y personalización del software para satisfacer las necesidades de
cada cliente este tipo de negocio permite generar ingresos recurrentes y que un gran número
de clientes, principalmente pequeños y medianos, puedan adoptar el sistema.


## Estrategia de marketing

La estrategia de marketing estará enfocada principalmente en medios digitales
utilizando redes sociales campañas publicitarias y demostraciones del sistema para captar
potenciales clientes, también se contempla realizar pruebas piloto en pequeños
supermercados para demostrar los beneficios de la solución asimismo se buscarán alianzas
con establecimientos comerciales interesados en optimizar sus procesos de inventario y
reducir pérdidas económicas asociadas al vencimiento de productos.


## Pitch – Video

https://www.youtube.com/watch?v=-1ZYEpSZkjg
La presentación de la situación problemática hace alusión al desperdicio de la
alimentación que afecta a Colombia donde al año se desperdician millones de toneladas de
comida lo que genera pérdidas económicas y agresiones medioambientales en 2007 se
expone que el impacto medioambiental asciende a unos 0,04 millones de dólares
disminuyendo hasta un total de 3,5 millones de dólares al verterse al océano lo que podría
haberse reducido, entonces, se presenta como solución un sistema inteligente de descuentos
dinámicos que automatiza apareciendo un descuento progresivo desde el mismo momento
que el producto comienza la cuenta atrás de su vida útil y cuando se acerca el final de su
vida útil y así dar prioridad a vender por un precio mínimamente inferior al precio de venta
inicial, el foco de la solución es el público objetivo que principalmente está orientado hacia
supermercados pequeños y tienditas de barrio donde la necesidad de minimizar el
desperdicio la necesidad de crear ventas a precios más bajos para los clientes está creciendo
debido a la bajada la caída de la venta de productos alimentarios, el modelo de negocio
plantea el ofrecer la venta con licencias del software y por otro lado establecer un sistema
de comisiones en función de las ventas generadas por la aplicación. desde el punto de vista
del marketing el crecimiento será nítido basado en un resultado positivo de la aplicación y
en las recomendaciones que irán generando los propios usuarios y los comercios, a su vez
la presentación presenta todo el orden de un equipo organizado en lo que se refiere a
desarrollos, operaciones y estrategia, por último el pitch concluye con el impacto de la
aplicación del sistema que se proyecta encaminado a transformar la gestión de inventarios


la reducción del desperdicio de alimentos y generar beneficios económicos y sociales para
el comercio y el cliente final.


## Desarrollo E Implementación

En la versión original esta sección describía funciones de un único programa
(dias_para_vencer, riesgo_por_vencimiento, eliminar_vencidos, escanear_inventario) y
las clases Usuario, Producto y Descuento. Con la arquitectura distribuida esa lógica se
reparte en módulos del servidor, y el cliente ya no contiene reglas de negocio.

### Arquitectura de dos nodos y capas

El servidor (carpeta server/) se ejecuta con `python -m server.main` (FastAPI y uvicorn, un
solo proceso) y se organiza en: api/ (rutas REST y el WebSocket), application/ (servicios y
casos de uso: InventarioService, VentaService, RiesgoService, ConfigService, UsuarioService
y el EventBus), domain/ (entidades y reglas puras, sin frameworks), infrastructure/db/ (modelos
SQLAlchemy, repositorios, migración desde la base antigua y datos iniciales) y security/ (argon2id,
JWT y sesiones). El cliente (carpeta client/) se ejecuta con `python -m client.main` (PyQt6) y
se organiza en presentation/ (vistas y widgets), application/ (controlador de sesión) e
infrastructure/ (api_client con httpx, event_client con QtWebSockets, idle_monitor y
workers). La carpeta shared/ contiene los modelos Pydantic del contrato entre ambos nodos y
el redondeo monetario, que usan los dos para que la vista previa del cliente coincida con la factura
del servidor.

### Módulo: server/domain/riesgo.py

Contiene las funciones puras de riesgo, sin base de datos ni reloj global (reciben la
fecha actual y la política como parámetros). dias_para_vencer calcula la diferencia en días de calendario
entre la fecha de vencimiento y hoy (None si el producto no tiene fecha). esta_vencido es
verdadero solo cuando la hora actual supera estrictamente la fecha y hora de vencimiento.
evaluar_producto combina el riesgo por vencimiento (Crítico si está vencido o a ≤ 3 días,
Alto a ≤ 7 días) y el riesgo por stock (sobrestock con descuento, stock bajo solo como
alerta) y devuelve el nivel, el motivo, el porcentaje de descuento y el precio final. Un
producto vencido no recibe descuento porque no se vende: se retira. Los umbrales y
porcentajes vienen de un objeto PoliticaRiesgo construido desde la configuración.

### Módulo: server/application/riesgo_service.py

RiesgoService.escanear reemplaza a las funciones eliminar_vencidos y escanear_inventario de la versión
original. En una sola transacción retira (baja lógica) los productos vencidos, desactiva
los descuentos huérfanos y sincroniza los descuentos activos con la evaluación vigente
(solo hay un descuento activo por producto); después de confirmar publica los eventos
productos_retirados y descuento_cambiado. La clase Scheduler lo ejecuta en un hilo daemon
cada intervalo_escaneo_segundos (60 por defecto, releído en cada ciclo) y sobrevive a las
excepciones. El mismo servicio entrega el resumen del dashboard, las alertas por severidad
y las ofertas del comprador (activos, no vencidos, con stock y con descuento).

### Módulo: server/application/venta_service.py

VentaService.comprar valida cada línea con el dominio (cantidad, producto activo, no vencido, stock),
calcula precios con la misma evaluación de riesgo, suma el IVA sobre el precio con descuento y, dentro de una
única transacción, descuenta el stock con una condición atómica (stock mayor o igual a la cantidad) y
crea la factura con su detalle. Si algo falla se revierte todo. Después de confirmar publica
stock_actualizado. Los cálculos de totales están en server/domain/facturacion.py y
server/domain/ventas.py.

### Módulo: server/security (sesiones, tokens y hashing)

hashing.py guarda las contraseñas con argon2id y verifica el formato antiguo sha256$ para
re-hashearlo en el primer ingreso. tokens.py emite y valida el JWT (HS256) con los datos
sub, rol, jti y exp; el secreto viene de una variable de entorno o de un archivo generado en el
primer arranque. sesiones.py (AuthService) crea una fila en la tabla sesiones por cada login y
en cada petición valida el token, que la sesión no esté cerrada y que el tiempo desde la última
actividad no supere inactividad_segundos (valor leído de la configuración en cada validación, por lo que
un cambio del administrador aplica a las sesiones abiertas). Solo el login y
POST /auth/actividad renuevan la actividad. Incluye el limitador de 5 intentos fallidos por
usuario con bloqueo de 60 s (en memoria).

### Cliente: client/ (hilos de red, inactividad y eventos)

client/infrastructure/workers.py ejecuta toda llamada de red en un hilo del QThreadPool y
devuelve el resultado al hilo gráfico. idle_monitor.py cuenta como actividad solo el teclado, los
clics, la rueda, los movimientos amplios del ratón y el cambio de vista; muestra el aviso, expira
la sesión con su propio temporizador y reporta la actividad al servidor con un máximo de una
vez cada 10 s. event_client.py mantiene el WebSocket, reconecta con espera creciente y
emite un sondeo de respaldo cada 60 s mientras no hay conexión. client/application/sesion.py
(clase Aplicacion) coordina el login, la ventana según el rol y todos los tipos de cierre
de sesión.

### Modelo de datos (server/infrastructure/db/orm.py)

La base SQLite tiene ocho tablas. usuarios guarda nombre, usuario único, password_hash
(argon2id), rol y activo. productos es la tabla central: el campo activo implementa la baja
lógica (nunca se borra un producto físicamente) y tiene restricciones CHECK (precio, stock y
stock máximo no negativos). descuentos registra el historial de descuentos con el porcentaje, el motivo
y si está activo; el servicio de riesgo desactiva el anterior antes de crear uno nuevo, de modo
que solo hay un descuento activo por producto. facturas y detalle_factura guardan la compra
(cabecera con cliente, método de pago, subtotal, ahorro, IVA, total, efectivo y cambio; y una
línea por producto con una copia del nombre, el precio, el descuento y el subtotal). sesiones guarda
el identificador del token (jti), la última actividad y el motivo del cierre. configuracion guarda
los parámetros como pares clave-valor y contadores guarda el consecutivo de facturas. Las claves
foráneas y las restricciones CHECK están activas en cada conexión.


## Solución

La solución propuesta se basa en una herramienta con diseño de aplicación de
escritorio (cliente) conectada a un servidor que se encarga de gestionar la problemática de forma automatizada con el
inventario de productos que son perecederos el sistema está orientado a registrar los
productos reconocer los que están próximos a la fecha de caducidad para aplicar un
descuento de forma automática en relación con unos parámetros de validación y por otro
lado mostrar en una interfaz los productos que están en oferta para poder tomar decisiones
de forma consciente tanto por parte de los empleados como por parte de las personas
consumidoras aunque esta primera fase es más inteligente y automatizada no estamos
considerando los sistemas de inteligencia artificial de última generación sino que estamos
considerando el uso de un prototipo concretamente sobre el que podamos validar la
viabilidad tanto técnica como operativa de la solución para dicha problemática.


## Proyección o impacto

Se espera que el proyecto contribuya a reducir el desperdicio de alimentos en
supermercados y mejorar la gestión de inventarios mediante procesos automatizados,
además del impacto económico positivo para los comercios el sistema puede generar
beneficios sociales y ambientales al promover un consumo más responsable y sostenible a
largo plazo el proyecto podría evolucionar hacia una solución más robusta e integrarse con
sistemas comerciales reales ampliando su alcance dentro del mercado tecnológico y
comercial.


## Conclusiones

El desarrollo del sistema inteligente para la aplicación de descuentos dinámicos en
los productos perecederos es prueba evidente que la integración de tecnologías basadas en
la inteligencia artificial junto a sistemas distribuidos conlleva una propuesta de soluciones a
problemáticas reales que tiene el sector de los supermercados se identificó que la apropiada
gestión de productos próximos a la fecha de caducidad es una de las causas fundamentales
de pérdida económica y por lo tanto de desperdicio de comida razón por la cual hacen falta
nuevas herramientas tecnológicas que ayuden a mejorar estos procesos.

En la misma línea se puede concluir que el uso de modelos de análisis predictivo y
la automatización ayudan a mejorar la toma de decisiones dentro de los supermercados al
anticiparse a situaciones de crisis y aplicar descuentos en productos que son críticos con
suficiente antelación, no sólo hace un impacto positivo en la rentabilidad, sino que también
ayuda a promover la sostenibilidad al ayudar a reducir el desperdicio de comida, logrando
beneficios duales, tanto económicos como sociales.

Por otro lado el análisis de mercado realizado pone de manifiesto que existe una
muy buena aceptación por parte de los consumidores hacia este tipo de soluciones debido a
la preocupación por el ahorro y el consumo responsable de sus recursos del mismo modo
existe una clara ventaja competitiva del sistema propuesto frente a las herramientas
tradicionales puesto que incluye elementos como la automatización y procesos relacionados
con la inteligencia artificial para gestionar el inventario.

Por lo que se recomienda continuar la tarea de desarrollo y mejora del sistema
incorporando nuevas funcionalidades y mejoras que hagan más posible su implementación
en entornos reales en este sentido la integración con otras tecnologías, como las apps


móviles o con los sistemas de facturación podría aumentar el potencial de software y la
experiencia del usuario final en este sentido el proyecto se configura como una solución
productiva, novedosa y acorde con las transformaciones tecnológicas actuales, de
transformación digital y sostenibilidad.


## Referencias Bibliográficas

Baryannis, G., Validi, S., Dani, S., & Antoniou, G. (2019). Supply chain risk
management and artificial intelligence: State of the art and future research directions.
_Computers in Industry, 113_ , 103179. https://doi.org/10.1016/j.compind.2019.103179

Dutta, P., Choi, T. M., Somani, S., & Butala, R. (2020). Big data and artificial intelligence
in supply chain management: A review and bibliometric analysis. _Journal of Cleaner
Production, 258_ , 120920. https://doi.org/10.1016/j.jclepro.2020.120920

Kamble, S. S., Gunasekaran, A., & Sharma, R. (2021). Modeling the blockchain
enabled traceability in agriculture supply chain. _Technological Forecasting and Social
Change, 166_ , 120880. https://doi.org/10.1016/j.techfore.2021.120880

Parfitt, J., Barthel, M., & Macnaughton, S. (2021). Food waste within food supply
chains: Quantification and potential for change. _Philosophical Transactions of the Royal
Society B_ , 376(1834). https://doi.org/10.1098/rstb.2021

Zhang, Y., Ren, S., Liu, Y., & Si, S. (2022). A big data analytics architecture for
cleaner manufacturing and maintenance processes. _Expert Systems with Applications, 186_ ,

115749. https://doi.org/10.1016/j.eswa.2022.115749

Ministerio de Ambiente y Desarrollo Sostenible. (2024). _Minambiente lanza
estrategia para frenar desperdicio de 10 millones de toneladas de alimentos_. Gobierno de
Colombia. https://www.minambiente.gov.co/minambiente-lanza-estrategia-para-frenar-
desperdicio-de- 10 - millones-de-toneladas-de-alimentos/