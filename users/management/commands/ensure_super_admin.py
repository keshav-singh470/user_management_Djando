import os

from django.core.management.base import BaseCommand, CommandError

from users.models import Profile, User


class Command(BaseCommand):
    help = "Create the first Super Admin from environment variables if none exists."

    def handle(self, *args, **options):
        # Do nothing if a Super Admin already exists
        if User.objects.filter(profiles__name='Super Admin').exists():
            self.stdout.write("Super Admin already exists. Nothing to do.")
            return

        email = os.getenv('SUPERADMIN_EMAIL')
        password = os.getenv('SUPERADMIN_PASSWORD')
        if not email or not password:
            raise CommandError("SUPERADMIN_EMAIL and SUPERADMIN_PASSWORD must be set.")

        profile = Profile.objects.filter(name='Super Admin').first()
        if not profile:
            raise CommandError("Profile 'Super Admin' not found. Run migrations first.")

        User.objects.create_superuser(
            username=email, email=email, password=password, profiles=profile
        )
        self.stdout.write(self.style.SUCCESS(f"Super Admin created: {email}"))