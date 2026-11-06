"""Crea un productor ficticio con un año de datos de demostración.

Uso:
    python manage.py seed_demo_data
    python manage.py seed_demo_data --reset
    python manage.py seed_demo_data --email demo@ejemplo.com --password "OtraClave2026!"

Genera dos fincas, lotes, trabajadores, tipos de actividad, jornadas,
recolecciones, liquidaciones/pagos, ventas y egresos operativos. Los datos
quedan repartidos en los últimos 12 meses (incluido el mes actual), de modo
que el cliente pueda probar listados, filtros, analíticas y reportes.
"""

import calendar
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.farms.models import Farm, Lot
from apps.finance.models import OperatingExpense
from apps.labor.models import (
    ActivityType,
    HarvestRecord,
    Worker,
    Workday,
    WorkdayDetail,
    WorkdayWorker,
)
from apps.payroll.models import (
    LaborPayment,
    Settlement,
    SettlementDetailHarvest,
    SettlementDetailWorkday,
)
from apps.payroll.services import PayrollService
from apps.production.models import Sale

User = get_user_model()

DEMO_EMAIL = "demo.productor@cafesmart.test"
DEMO_PASSWORD = "DemoCafe2026!"
DEMO_FIRST_NAME = "Camilo"
DEMO_LAST_NAME = "Restrepo"
DEMO_PHONE = "300 555 0187"


def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def kilograms(value):
    return Decimal(str(value)).quantize(Decimal("0.001"))


class Command(BaseCommand):
    help = "Crea un usuario productor ficticio con un año de datos de prueba."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            default=DEMO_EMAIL,
            help=f"Correo del usuario ficticio (por defecto: {DEMO_EMAIL}).",
        )
        parser.add_argument(
            "--password",
            default=DEMO_PASSWORD,
            help="Contraseña del usuario ficticio.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Elimina los datos del usuario ficticio si ya existe y los vuelve a crear.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=2026,
            help="Semilla del generador aleatorio para obtener datos reproducibles.",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        password = options["password"]
        reset = options["reset"]
        rng = random.Random(options["seed"])
        today = timezone.localdate()

        existing = User.objects.filter(email=email).first()
        if existing and not reset:
            raise CommandError(
                f"El usuario {email} ya existe. Usa --reset para borrar sus datos "
                "y volver a generarlos."
            )

        with transaction.atomic():
            if existing:
                self._delete_demo_data(existing)
            summary = self._create_demo_data(
                email=email,
                password=password,
                rng=rng,
                today=today,
            )

        self._print_report(email=email, password=password, summary=summary)

    # ------------------------------------------------------------------
    # Borrado
    # ------------------------------------------------------------------
    def _delete_demo_data(self, user):
        farm_ids = list(
            Farm.objects.filter(id_productor=user).values_list("id", flat=True)
        )

        # El orden respeta las relaciones PROTECT del modelo.
        OperatingExpense.objects.filter(farm_id__in=farm_ids).delete()
        LaborPayment.objects.filter(settlement__farm_id__in=farm_ids).delete()
        SettlementDetailWorkday.objects.filter(
            settlement__farm_id__in=farm_ids
        ).delete()
        SettlementDetailHarvest.objects.filter(
            settlement__farm_id__in=farm_ids
        ).delete()
        Settlement.objects.filter(farm_id__in=farm_ids).delete()
        HarvestRecord.objects.filter(
            workday_detail__workday_worker__workday__producer=user
        ).delete()
        WorkdayDetail.objects.filter(
            workday_worker__workday__producer=user
        ).delete()
        WorkdayWorker.objects.filter(workday__producer=user).delete()
        Workday.objects.filter(producer=user).delete()
        Sale.objects.filter(farm_id__in=farm_ids).delete()
        Lot.objects.filter(id_farm_id__in=farm_ids).delete()
        Farm.objects.filter(id_productor=user).delete()
        Worker.objects.filter(producer=user).delete()
        ActivityType.objects.filter(producer=user).delete()
        user.delete()

    # ------------------------------------------------------------------
    # Creación
    # ------------------------------------------------------------------
    def _create_demo_data(self, *, email, password, rng, today):
        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=DEMO_FIRST_NAME,
            last_name=DEMO_LAST_NAME,
            phone_number=DEMO_PHONE,
            role=UserRole.PRODUCER,
        )

        farms = self._create_farms(user)
        workers = self._create_workers(user, rng)
        activities = self._create_activities(user)

        totals = {
            "workdays": 0,
            "participations": 0,
            "details": 0,
            "harvests": 0,
            "settlements": 0,
            "payments": 0,
            "sales": 0,
            "expenses": 0,
        }

        current_month = today.replace(day=1)
        start_month = self._add_months(current_month, -11)
        month_cursor = start_month
        while month_cursor <= current_month:
            totals = self._generate_month(
                user=user,
                farms=farms,
                workers=workers,
                activities=activities,
                rng=rng,
                today=today,
                month_start=month_cursor,
                is_current_month=(month_cursor == current_month),
                totals=totals,
            )
            month_cursor = self._add_months(month_cursor, 1)

        return totals

    def _create_farms(self, user):
        la_esperanza = Farm.objects.create(
            id_productor=user,
            name="Finca La Esperanza",
            location="Salgar, Antioquia",
            description=(
                "Finca cafetera de ladera con café Castillo y Caturra. "
                "Cuenta con beneficio propio y secadero solar."
            ),
        )
        el_roble = Farm.objects.create(
            id_productor=user,
            name="Finca El Roble",
            location="Ciudad Bolívar, Antioquia",
            description=(
                "Finca de media montaña con variedades Tabi y Borbón. "
                "Producción principalmente de café pergamino seco."
            ),
        )

        lots = {
            la_esperanza.id: [
                dict(
                    name="El Mirador",
                    coffee_variety="Castillo",
                    area_m2=Decimal("32000.00"),
                    plant_count=4200,
                    description="Lote principal, expuesto al sol de la mañana.",
                ),
                dict(
                    name="La Quebrada",
                    coffee_variety="Caturra",
                    area_m2=Decimal("28000.00"),
                    plant_count=3600,
                    description="Lote junto a la quebrada, con sombra parcial.",
                ),
                dict(
                    name="El Trapiche",
                    coffee_variety="Colombia",
                    area_m2=Decimal("18000.00"),
                    plant_count=2400,
                    description="Lote renovado en 2024.",
                ),
            ],
            el_roble.id: [
                dict(
                    name="Alto Bonito",
                    coffee_variety="Tabi",
                    area_m2=Decimal("24000.00"),
                    plant_count=3100,
                    description="Lote alto, ideal para café de especialidad.",
                ),
                dict(
                    name="El Chorro",
                    coffee_variety="Borbón",
                    area_m2=Decimal("20000.00"),
                    plant_count=2600,
                    description="Lote con pendiente moderada y buen drenaje.",
                ),
            ],
        }

        for farm in (la_esperanza, el_roble):
            for lot_data in lots[farm.id]:
                Lot.objects.create(id_farm=farm, **lot_data)

        return list(Farm.objects.filter(id_productor=user).order_by("name"))

    def _create_workers(self, user, rng):
        people = [
            ("José Antonio", "Ramírez", "DEMO-CC-1001", "310 555 1001"),
            ("María Elena", "Gómez", "DEMO-CC-1002", "310 555 1002"),
            ("Luis Fernando", "Cardona", "DEMO-CC-1003", "310 555 1003"),
            ("Ana Lucía", "Restrepo", "DEMO-CC-1004", "310 555 1004"),
            ("Carlos Mario", "Henao", "DEMO-CC-1005", "310 555 1005"),
            ("Gloria Patricia", "Muñoz", "DEMO-CC-1006", "310 555 1006"),
            ("Andrés Felipe", "Ospina", "DEMO-CC-1007", "310 555 1007"),
            ("Sandra Milena", "Ríos", "DEMO-CC-1008", "310 555 1008"),
        ]
        workers = [
            Worker.objects.create(
                producer=user,
                first_name=first_name,
                last_name=last_name,
                identification=identification,
                phone=phone,
                is_active=True,
            )
            for first_name, last_name, identification, phone in people
        ]
        # El orden aleatorio evita que siempre trabajen los mismos en cada finca.
        rng.shuffle(workers)
        return workers

    def _create_activities(self, user):
        harvest = ActivityType.objects.create(
            producer=user,
            name="Recolección de café",
            description="Recolección manual y pesaje de café cereza.",
            is_harvest=True,
        )
        maintenance = [
            ActivityType.objects.create(
                producer=user,
                name="Abonar cafetal",
                description="Aplicación de fertilizante y enmiendas.",
            ),
            ActivityType.objects.create(
                producer=user,
                name="Limpiar maleza",
                description="Control manual de arvenses en los lotes.",
            ),
            ActivityType.objects.create(
                producer=user,
                name="Podar cafetos",
                description="Poda de formación y saneamiento.",
            ),
            ActivityType.objects.create(
                producer=user,
                name="Mantenimiento de lotes",
                description="Reparación de caminos, drenajes y cercas.",
            ),
        ]
        return {"harvest": harvest, "maintenance": maintenance}

    # ------------------------------------------------------------------
    # Generación mensual
    # ------------------------------------------------------------------
    def _generate_month(
        self,
        *,
        user,
        farms,
        workers,
        activities,
        rng,
        today,
        month_start,
        is_current_month,
        totals,
    ):
        year, month = month_start.year, month_start.month
        last_day = calendar.monthrange(year, month)[1]
        month_end = date(year, month, last_day)

        # Participaciones y pesajes agrupados por (finca, trabajador) para
        # liquidarlos al final del mes.
        pending_by_worker = {}
        production_by_farm = {farm.id: Decimal("0.000") for farm in farms}

        for farm in farms:
            lots = list(farm.lots.filter(is_active=True))
            workday_dates = self._workday_dates(year, month, today)

            for workday_date in workday_dates:
                is_harvest_day = workday_date.weekday() == 1  # martes
                workday = Workday.objects.create(
                    producer=user,
                    farm=farm,
                    date=workday_date,
                    status=Workday.Status.CLOSED,
                    closed_at=timezone.make_aware(
                        datetime.combine(workday_date, time(17, 0))
                    ),
                )
                totals["workdays"] += 1

                participant_count = rng.randint(2, 4)
                selected_workers = rng.sample(workers, participant_count)

                for worker in selected_workers:
                    # En días de cosecha casi todos se pagan por kilogramo;
                    # ocasionalmente un trabajador se paga por jornal.
                    if is_harvest_day and rng.random() < 0.82:
                        payment_mode = WorkdayWorker.PaymentMode.KILOGRAM
                        rate = money(rng.randint(1000, 1450))
                    elif is_harvest_day:
                        payment_mode = WorkdayWorker.PaymentMode.DAILY
                        rate = money(rng.randint(58000, 72000))
                    else:
                        payment_mode = WorkdayWorker.PaymentMode.DAILY
                        rate = money(rng.randint(58000, 72000))

                    participation = WorkdayWorker.objects.create(
                        worker=worker,
                        workday=workday,
                        payment_mode=payment_mode,
                        agreed_rate=rate,
                        settlement_status=WorkdayWorker.SettlementStatus.PENDING,
                    )
                    totals["participations"] += 1

                    if is_harvest_day:
                        activity = activities["harvest"]
                    else:
                        activity = rng.choice(activities["maintenance"])

                    detail = WorkdayDetail.objects.create(
                        activity_type=activity,
                        workday_worker=participation,
                        lot=rng.choice(lots),
                    )
                    totals["details"] += 1

                    key = (farm.id, worker.id)
                    bucket = pending_by_worker.setdefault(key, [])
                    if payment_mode == WorkdayWorker.PaymentMode.DAILY:
                        bucket.append(("workday", participation))

                    if payment_mode == WorkdayWorker.PaymentMode.KILOGRAM:
                        if month in (5, 6, 7, 10, 11, 12):
                            quantity = rng.uniform(25, 48)
                        else:
                            quantity = rng.uniform(10, 24)
                        quantity = kilograms(quantity)
                        harvest_time = time(
                            rng.randint(8, 15),
                            rng.choice((0, 10, 15, 20, 30, 40, 45)),
                        )
                        harvest = HarvestRecord.objects.create(
                            workday_detail=detail,
                            quantity_kg=quantity,
                            time=harvest_time,
                            settlement_status=HarvestRecord.SettlementStatus.REGISTERED,
                        )
                        totals["harvests"] += 1
                        production_by_farm[farm.id] += quantity
                        bucket.append(("harvest", harvest))

            # Ventas y egresos del mes para esta finca.
            totals["sales"] += self._create_sales(
                farm=farm,
                rng=rng,
                year=year,
                month=month,
                today=today,
                month_start=month_start,
                month_end=month_end,
                produced_kg=production_by_farm[farm.id],
            )
            totals["expenses"] += self._create_expenses(
                farm=farm,
                rng=rng,
                year=year,
                month=month,
                today=today,
                month_start=month_start,
                month_end=month_end,
            )

        # Las liquidaciones del mes actual se dejan abiertas/pendientes para
        # poder probar los flujos de "pendientes" y de liquidación en el cliente.
        if not is_current_month:
            settlement_totals = self._settle_month(
                user=user,
                farms=farms,
                workers=workers,
                rng=rng,
                today=today,
                month_start=month_start,
                month_end=month_end,
                pending_by_worker=pending_by_worker,
            )
            totals["settlements"] += settlement_totals["settlements"]
            totals["payments"] += settlement_totals["payments"]

        return totals

    def _workday_dates(self, year, month, today):
        """Martes y viernes de cada mes, sin incluir fechas futuras."""
        dates = []
        day = date(year, month, 1)
        while day.month == month:
            if day <= today and day.weekday() in (1, 4):
                dates.append(day)
            day += timedelta(days=1)
        return dates

    def _settle_month(
        self,
        *,
        user,
        farms,
        workers,
        rng,
        today,
        month_start,
        month_end,
        pending_by_worker,
    ):
        farm_by_id = {farm.id: farm for farm in farms}
        worker_by_id = {worker.id: worker for worker in workers}
        settlements = 0
        payments = 0

        next_month = self._add_months(month_start, 1)
        payment_day = date(next_month.year, next_month.month, 5)
        if payment_day > today:
            payment_day = today

        for (farm_id, worker_id), items in sorted(
            pending_by_worker.items(), key=lambda entry: (str(entry[0][0]), str(entry[0][1]))
        ):
            farm = farm_by_id[farm_id]
            worker = worker_by_id[worker_id]
            settlement = Settlement.objects.create(
                worker=worker,
                farm=farm,
                start_date=month_start,
                end_date=month_end,
            )

            for kind, item in items:
                if kind == "workday":
                    PayrollService.add_workday_to_settlement(
                        settlement_id=settlement.id,
                        workday_worker_id=item.id,
                    )
                else:
                    PayrollService.add_harvest_to_settlement(
                        settlement_id=settlement.id,
                        harvest_record_id=item.id,
                    )

            settlement = PayrollService.close_settlement(
                settlement_id=settlement.id
            )
            if settlement.total_calculated <= 0:
                continue

            PayrollService.pay_settlement(
                settlement_id=settlement.id,
                date=payment_day,
                amount_paid=settlement.total_calculated,
                payment_method=rng.choice(
                    [
                        LaborPayment.PaymentMethod.TRANSFER,
                        LaborPayment.PaymentMethod.TRANSFER,
                        LaborPayment.PaymentMethod.CASH,
                    ]
                ),
                notes="Pago de liquidación mensual (dato de demostración).",
            )
            settlements += 1
            payments += 1

        return {"settlements": settlements, "payments": payments}

    # ------------------------------------------------------------------
    # Ventas y egresos
    # ------------------------------------------------------------------
    def _create_sales(
        self,
        *,
        farm,
        rng,
        year,
        month,
        today,
        month_start,
        month_end,
        produced_kg,
    ):
        if produced_kg <= 0:
            return 0

        sale_end = min(month_end, today)
        sale_start = month_start

        buyers = [
            "Cooperativa Cafetera de Occidente",
            "Trilladora La Montaña",
            "Exportadora Andina S.A.S.",
            "Comercializadora El Cafetal",
            "Comprador local - plaza de Salgar",
        ]

        # Se vende entre el 60 % y el 85 % de la producción del mes.
        sold_kg = kilograms(produced_kg * Decimal(str(rng.uniform(0.60, 0.85))))
        if sold_kg <= 0:
            return 0

        base_price = Decimal(str(rng.randint(14500, 19500)))
        sale_date = self._random_date(rng, sale_start, sale_end)
        Sale.objects.create(
            farm=farm,
            sale_date=sale_date,
            coffee_type=Sale.CoffeeType.PERGAMINO,
            quantity_kg=sold_kg,
            unit_price=money(base_price),
            total_amount=money(sold_kg * base_price),
            buyer=rng.choice(buyers),
            notes="Venta de café pergamino seco (dato de demostración).",
            is_active=True,
        )
        sales = 1

        # Ocasionalmente se vende pasilla a menor precio.
        if rng.random() < 0.30:
            pasilla_kg = kilograms(sold_kg * Decimal(str(rng.uniform(0.03, 0.07))))
            pasilla_price = money(rng.randint(2800, 4800))
            Sale.objects.create(
                farm=farm,
                sale_date=self._random_date(rng, sale_start, sale_end),
                coffee_type=Sale.CoffeeType.PASILLA,
                quantity_kg=pasilla_kg,
                unit_price=pasilla_price,
                total_amount=money(pasilla_kg * pasilla_price),
                buyer=rng.choice(buyers),
                notes="Venta de pasilla (dato de demostración).",
                is_active=True,
            )
            sales += 1

        return sales

    def _create_expenses(
        self,
        *,
        farm,
        rng,
        year,
        month,
        today,
        month_start,
        month_end,
    ):
        created = 0
        expense_end = min(month_end, today)

        def add(concept, category, low, high):
            nonlocal created
            amount = money(rng.randint(low, high))
            OperatingExpense.objects.create(
                farm=farm,
                date=self._random_date(rng, month_start, expense_end),
                concept=concept,
                amount=amount,
                category=category,
            )
            created += 1

        add(
            rng.choice(
                [
                    "Herramientas menores y repuestos",
                    "Guantes, botas y equipo de protección",
                    "Combustible para guadañadora",
                ]
            ),
            OperatingExpense.Category.TOOLS_MATERIALS,
            80000,
            380000,
        )
        add(
            rng.choice(
                [
                    "Transporte de café al beneficio",
                    "Flete de insumos a la finca",
                    "Combustible para transporte interno",
                ]
            ),
            OperatingExpense.Category.TRANSPORT,
            70000,
            280000,
        )
        add(
            rng.choice(
                [
                    "Energía eléctrica",
                    "Internet rural",
                    "Mantenimiento del beneficio",
                ]
            ),
            OperatingExpense.Category.SERVICES,
            80000,
            320000,
        )

        if month in (2, 4, 6, 8, 10, 12):
            add(
                rng.choice(
                    [
                        "Fertilizante NPK",
                        "Abono orgánico compostado",
                        "Cal agrícola y enmiendas",
                    ]
                ),
                OperatingExpense.Category.INPUTS,
                900000,
                1800000,
            )
        if month % 2 == 0:
            add(
                rng.choice(
                    [
                        "Cuota de asociación cafetera",
                        "Certificación de café",
                        "Imprevistos de la finca",
                    ]
                ),
                OperatingExpense.Category.OTHER,
                50000,
                240000,
            )

        return created

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    @staticmethod
    def _add_months(value, months):
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    @staticmethod
    def _random_date(rng, start, end):
        if start >= end:
            return end
        return start + timedelta(days=rng.randint(0, (end - start).days))

    def _print_report(self, *, email, password, summary):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Datos de demostración creados."))
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Credenciales"))
        self.stdout.write(f"  Correo:    {email}")
        self.stdout.write(f"  Contraseña: {password}")
        self.stdout.write(f"  Rol:       {UserRole.PRODUCER}")
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Registros generados"))
        self.stdout.write(f"  Jornadas:                {summary['workdays']}")
        self.stdout.write(f"  Participaciones:         {summary['participations']}")
        self.stdout.write(f"  Detalles de jornada:     {summary['details']}")
        self.stdout.write(f"  Pesajes/recolecciones:   {summary['harvests']}")
        self.stdout.write(f"  Liquidaciones pagadas:   {summary['settlements']}")
        self.stdout.write(f"  Pagos laborales:         {summary['payments']}")
        self.stdout.write(f"  Ventas:                  {summary['sales']}")
        self.stdout.write(f"  Egresos operativos:      {summary['expenses']}")
        self.stdout.write("")
        self.stdout.write(
            "Inicia sesión en POST /accounts/login/ con esas credenciales."
        )
        self.stdout.write("")
