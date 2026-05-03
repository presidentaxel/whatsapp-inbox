-- Accès à l’onglet Playground (/playground) - aligné sur le modèle Axelia (overrides + rôles).
insert into app_permissions (code, label, description)
values (
  'playground.access',
  'Accès au Playground',
  'Voir et utiliser l’onglet scénarios / assistant Playground (/playground)'
)
on conflict (code) do update set
  label = excluded.label,
  description = excluded.description;

insert into role_permissions (role_id, permission_code)
select r.id, 'playground.access'
from app_roles r
where r.slug in ('admin', 'dev', 'manager')
on conflict do nothing;
