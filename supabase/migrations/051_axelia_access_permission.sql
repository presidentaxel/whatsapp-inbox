-- Permission d'accès au hub IA Axelia (/axelia) - désactivée par défaut pour les managers.
insert into app_permissions (code, label, description)
values (
  'axelia.access',
  'Accès à Axelia',
  'Voir et utiliser l''assistant IA Axelia dans l''application'
)
on conflict (code) do update set
  label = excluded.label,
  description = excluded.description;

insert into role_permissions (role_id, permission_code)
select r.id, 'axelia.access'
from app_roles r
where r.slug in ('admin', 'dev')
on conflict do nothing;
