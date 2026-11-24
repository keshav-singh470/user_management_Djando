import tempfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from .models import ActivityLog, LookupValue, Profile, Project, ProjectTask, User

PASSWORD = 'Pass@12345'
SUPERADMIN_EMAIL = 'superadmin@test.com'
SUPERADMIN_PASSWORD = 'SuperAdmin@123'
ROLES = ['Super Admin', 'Admin', 'Human Resource', 'Manager', 'Team Leader', 'Developer', 'Client']


def lookup(category, name):
    obj = LookupValue.objects.filter(category=category, name__iexact=name).first()
    return obj or LookupValue.objects.create(category=category, name=name, is_default=True)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())          # uploaded test files go to a temp folder
class BaseTest(APITestCase):
    def setUp(self):
        cache.clear()                                      # no leftover login or OTP counters
        self.profiles = {r: Profile.objects.get_or_create(name=r)[0] for r in ROLES}
        self.admin = self.make_user('admin', 'Admin')
        self.superadmin = self.make_user('superadmin', 'Super Admin', password=SUPERADMIN_PASSWORD)
        self.hr = self.make_user('hr', 'Human Resource')
        self.manager = self.make_user('manager', 'Manager')
        self.manager2 = self.make_user('manager2', 'Manager')
        self.tl = self.make_user('tl', 'Team Leader')
        self.tl2 = self.make_user('tl2', 'Team Leader')
        self.dev = self.make_user('dev', 'Developer')
        self.dev2 = self.make_user('dev2', 'Developer')
        self.client_user = self.make_user('client', 'Client')

        self.pending = lookup('task_status', 'Pending')
        lookup('task_status', 'Completed')
        self.project = Project.objects.create(
            title='Portal', type=lookup('project_type', 'Web App'), status=lookup('project_status', 'Pending'),
            assigned_manager=self.manager, created_by=self.admin)
        self.project.team_leaders.add(self.tl)

    def make_user(self, key, role, password=PASSWORD):
        return User.objects.create_user(
            username=f'{key}@test.com', email=f'{key}@test.com', password=password, first_name=key,
            profiles=self.profiles[role], company_name='Acme' if role == 'Client' else None)

    def as_user(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def make_task(self, creator=None, assignee=None, title='Build login page'):
        return ProjectTask.objects.create(
            project=self.project, title=title, assigned_to=assignee or self.dev, created_by=creator or self.tl,
            status=self.pending, start_date='2026-12-01', deadline_date='2026-12-10')

    def task_payload(self, assignee=None):
        return {'title': 'Login page', 'start_date': '2026-12-01', 'deadline_date': '2026-12-10',
                'assigned_to': (assignee or self.dev).id}


class PermissionTests(BaseTest):
    def test_admin_can_create_project(self):
        r = self.as_user(self.admin).post('/api/projects/', {'title': 'New App', 'type': 'Web App'}, format='json')
        self.assertEqual(r.status_code, 201)

    def test_manager_cannot_create_project(self):
        r = self.as_user(self.manager).post('/api/projects/', {'title': 'New App', 'type': 'Web App'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_developer_cannot_create_project(self):
        r = self.as_user(self.dev).post('/api/projects/', {'title': 'New App', 'type': 'Web App'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_hr_cannot_give_admin_profile(self):
        r = self.as_user(self.hr).post(
            '/api/users/', {'email': 'new@test.com', 'first_name': 'New', 'profiles': 'Admin'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_hr_can_create_developer(self):
        r = self.as_user(self.hr).post(
            '/api/users/', {'email': 'new@test.com', 'first_name': 'New', 'profiles': 'Developer'}, format='json')
        self.assertEqual(r.status_code, 201)


class TeamFlowTests(BaseTest):
    def test_manager_assigns_team_leader(self):
        self.project.team_leaders.clear()
        r = self.as_user(self.manager).post(
            f'/api/projects/{self.project.id}/team-leaders/', {'team_leaders': [self.tl.id]}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.project.team_leaders.filter(pk=self.tl.pk).exists())

    def test_developer_cannot_be_team_leader(self):
        r = self.as_user(self.manager).post(
            f'/api/projects/{self.project.id}/team-leaders/', {'team_leaders': [self.dev.id]}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_other_manager_cannot_manage_team_leaders(self):
        r = self.as_user(self.manager2).post(
            f'/api/projects/{self.project.id}/team-leaders/', {'team_leaders': [self.tl2.id]}, format='json')
        self.assertEqual(r.status_code, 404)

    def test_team_leader_creates_task_for_developer(self):
        r = self.as_user(self.tl).post(f'/api/projects/{self.project.id}/tasks/', self.task_payload(), format='json')
        self.assertEqual(r.status_code, 201)

    def test_task_cannot_go_to_team_leader(self):
        r = self.as_user(self.tl).post(
            f'/api/projects/{self.project.id}/tasks/', self.task_payload(self.tl2), format='json')
        self.assertEqual(r.status_code, 400)

    def test_manager_cannot_create_task(self):
        r = self.as_user(self.manager).post(
            f'/api/projects/{self.project.id}/tasks/', self.task_payload(), format='json')
        self.assertEqual(r.status_code, 403)

    def test_unassigned_team_leader_cannot_create_task(self):
        r = self.as_user(self.tl2).post(
            f'/api/projects/{self.project.id}/tasks/', self.task_payload(), format='json')
        self.assertEqual(r.status_code, 404)

    def test_client_cannot_create_task(self):
        r = self.as_user(self.client_user).post(
            f'/api/projects/{self.project.id}/tasks/', self.task_payload(), format='json')
        self.assertEqual(r.status_code, 403)


class VisibilityTests(BaseTest):
    def test_team_leader_does_not_see_another_leaders_task(self):
        self.project.team_leaders.add(self.tl2)
        task = self.make_task(creator=self.tl)
        self.assertEqual(self.as_user(self.tl).get(f'/api/tasks/{task.id}/').status_code, 200)
        self.assertEqual(self.as_user(self.tl2).get(f'/api/tasks/{task.id}/').status_code, 404)

    def test_developer_sees_only_own_task(self):
        task = self.make_task(assignee=self.dev)
        self.assertEqual(self.as_user(self.dev).get(f'/api/tasks/{task.id}/').status_code, 200)
        self.assertEqual(self.as_user(self.dev2).get(f'/api/tasks/{task.id}/').status_code, 404)

    def test_manager_sees_team_and_developer_is_blocked(self):
        self.make_task()
        r = self.as_user(self.manager).get(f'/api/projects/{self.project.id}/team/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['team_leaders'][0]['developers'][0]['name'], 'dev')
        self.assertEqual(self.as_user(self.manager).get('/api/projects/team-overview/').data['count'], 1)
        self.assertEqual(self.as_user(self.dev).get('/api/projects/team-overview/').status_code, 403)


class AuthTests(BaseTest):
    def login(self, password=PASSWORD):
        return self.client.post('/api/auth/login/', {'email': 'dev@test.com', 'password': password}, format='json')

    def test_login_returns_tokens(self):
        r = self.login()
        self.assertEqual(r.status_code, 200)
        self.assertIn('access', r.data)

    def test_login_locks_after_five_wrong_passwords(self):
        for _ in range(5):
            self.assertEqual(self.login('wrong-password').status_code, 401)
        self.assertEqual(self.login().status_code, 429)          # even the right password is refused now

    def test_logout_blocks_the_refresh_token(self):
        tokens = self.login().data
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + tokens['access'])
        r = self.client.post('/api/auth/logout/', {'refresh': tokens['refresh']}, format='json')
        self.assertEqual(r.status_code, 200)
        self.client.credentials()
        r = self.client.post('/api/auth/refresh/', {'refresh': tokens['refresh']}, format='json')
        self.assertEqual(r.status_code, 401)


class ActivityTests(BaseTest):
    def test_status_change_is_logged_and_visible_to_manager(self):
        task = self.make_task()
        r = self.as_user(self.dev).patch(f'/api/tasks/{task.id}/', {'status': 'Completed'}, format='json')
        self.assertEqual(r.status_code, 200)
        log = ActivityLog.objects.filter(task=task, action='updated').first()
        self.assertIn('Pending -> Completed', log.description)
        r = self.as_user(self.manager).get(f'/api/projects/{self.project.id}/activity/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['count'], 1)


class AttachmentTests(BaseTest):
    def upload(self, user, task, filename='notes.txt'):
        return self.as_user(user).post(
            f'/api/tasks/{task.id}/attachments/',
            {'files': SimpleUploadedFile(filename, b'hello')}, format='multipart')

    def test_assignee_can_upload(self):
        task = self.make_task()
        self.assertEqual(self.upload(self.dev, task).status_code, 201)

    def test_client_cannot_upload(self):
        task = self.make_task()
        self.assertEqual(self.upload(self.client_user, task).status_code, 403)

    def test_wrong_file_type_is_rejected(self):
        task = self.make_task()
        self.assertEqual(self.upload(self.dev, task, 'virus.exe').status_code, 400)


class SuperAdminTests(BaseTest):
    def test_super_admin_can_login(self):
        r = self.client.post('/api/auth/login/',
                             {'email': SUPERADMIN_EMAIL, 'password': SUPERADMIN_PASSWORD}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['user']['role'], 'Super Admin')

    def test_super_admin_can_hard_delete_project(self):
        r = self.as_user(self.superadmin).delete(f'/api/projects/{self.project.id}/?hard=true')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Project.objects.filter(pk=self.project.id).exists())

    def test_admin_cannot_hard_delete_project(self):
        r = self.as_user(self.admin).delete(f'/api/projects/{self.project.id}/?hard=true')
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Project.objects.filter(pk=self.project.id).exists())