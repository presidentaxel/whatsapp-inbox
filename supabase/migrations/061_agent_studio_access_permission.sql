-- Accès à l’onglet Agent Studio (/agent-studio)
-- Aligné sur le modèle Axelia/Playground avec overrides globaux.

insert into app_permissions (code, label, description)
values (
  'agent_studio.access',
  'Accès Agent Studio',
  'Voir et utiliser la page Agent Studio (/agent-studio)'
)
on conflict (code) do update set
  label = excluded.label,
  description = excluded.description;

insert into role_permissions (role_id, permission_code)
select r.id, 'agent_studio.access'
from app_roles r
where r.slug in ('admin', 'dev', 'manager')
on conflict do nothing;

