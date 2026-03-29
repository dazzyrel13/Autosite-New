from app import create_app
from extensions import db
from models import Vehicle
from decimal import Decimal


def seed_data():
    app = create_app()
    with app.app_context():
        # Drop and recreate for a clean start during development/fix
        import os
        if os.getenv('FLASK_DEBUG', 'True').lower() == 'false':
            print("CRITICAL: SEED_DB IS DISABLED IN PRODUCTION MODE (DEBUG=False)")
            return

        db.drop_all()
        db.create_all()

        vehicles = [
            Vehicle(
                category='cars_used',
                brand='Honda',
                model='Fit',
                price=Decimal('1232430'),
                year=2021,
                mileage=20000,
                engine_vol=1.5,
                power=130,
                badge='С пробегом',
                description=(
                    'Отличный городской автомобиль в прекрасном состоянии. '
                    'Экономичный и надежный.'
                ),
                specifications=[
                    {"name": "Привод", "value": "Передний"},
                    {"name": "Трансмиссия", "value": "Вариатор"},
                    {"name": "Цвет", "value": "Белый"}
                ],
                slug='honda-fit',
                main_image='images/cars/used/honda_fit_/honda_fit_1.webp',
                images=[
                    'images/cars/used/honda_fit_/honda_fit_1.webp',
                    'images/cars/used/honda_fit_/honda_fit_2.webp',
                    'images/cars/used/honda_fit_/honda_fit_3.webp',
                    'images/cars/used/honda_fit_/honda_fit_4.webp',
                    'images/cars/used/honda_fit_/honda_fit_5.webp'
                ]
            ),
            Vehicle(
                category='cars_new',
                brand='Audi',
                model='Q7 55 TFSI Quattro',
                price=Decimal('12950000'),
                year=2025,
                mileage=0,
                engine_vol=3.0,
                power=340,
                badge='Новый',
                description=(
                    'Роскошный кроссовер с непревзойденным уровнем комфорта '
                    'и динамики. Полный привод Quattro.'
                ),
                specifications=[
                    {"name": "Привод", "value": "Полный"},
                    {"name": "Трансмиссия", "value": "АКПП"},
                    {"name": "Топливо", "value": "Бензин"}
                ],
                slug='audi-q7',
                main_image='images/cars/new/Audi_Q7_55TFSI_QUATRO_/Audi_Q7_55TFSI_QUATRO1.jpg',
                images=['images/cars/new/Audi_Q7_55TFSI_QUATRO_/Audi_Q7_55TFSI_QUATRO1.jpg']
            ),
            Vehicle(
                category='trucks_tractors',
                brand='Foton',
                model='Galaxy 6x4',
                price=Decimal('15950000'),
                year=2025,
                mileage=0,
                engine_vol=13.0,
                power=450,
                badge='Новый',
                description=(
                    'Мощный и современный тягач для дальних перевозок. '
                    'Высокий уровень комфорта кабины.'
                ),
                specifications=[
                    {"name": "Колесная формула", "value": "6x4"},
                    {"name": "Экологический класс", "value": "Евро-5"},
                    {"name": "КПП", "value": "Робот"}
                ],
                slug='foton-galaxy',
                main_image='images/trucks_tractors/Foton_Galaxy_6x4/foton_galaxy_6_4_1.jpg',
                images=[
                    'images/trucks_tractors/Foton_Galaxy_6x4/foton_galaxy_6_4_1.jpg',
                    'images/trucks_tractors/Foton_Galaxy_6x4/foton_galaxy_6_4_2.jpg',
                    'images/trucks_tractors/Foton_Galaxy_6x4/foton_galaxy_6_4_3.jpg'
                ]
            )
        ]

        db.session.add_all(vehicles)
        db.session.commit()
        print("Database seeded successfully!")


if __name__ == '__main__':
    seed_data()
