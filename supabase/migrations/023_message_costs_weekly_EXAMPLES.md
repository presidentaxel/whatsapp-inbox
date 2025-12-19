# Exemples d'utilisation des coûts hebdomadaires

## Vue simple : Coûts totaux par semaine (tous comptes)

```sql
-- Voir tous les coûts hebdomadaires
SELECT * FROM message_costs_weekly
ORDER BY week_start DESC
LIMIT 10;
```

## Vue détaillée : Coûts par compte et par semaine

```sql
-- Voir les coûts hebdomadaires par compte
SELECT * FROM message_costs_weekly_by_account
ORDER BY week_start DESC, account_name;
```

## Fonction avec filtres

```sql
-- Coûts de la semaine en cours
SELECT * FROM get_weekly_costs(
  p_week_start => date_trunc('week', CURRENT_DATE)::date
);

-- Coûts d'un compte spécifique pour toutes les semaines
SELECT * FROM get_weekly_costs(
  p_account_id => 'votre-account-id-ici'::uuid
);

-- Coûts d'un compte spécifique pour une semaine spécifique
SELECT * FROM get_weekly_costs(
  p_week_start => '2024-01-01'::date,
  p_account_id => 'votre-account-id-here'::uuid
);
```

## Requête personnalisée avec agrégations

```sql
-- Coûts totaux des 4 dernières semaines
SELECT 
  week_start,
  year,
  week_number,
  SUM(total_cost) as total_cost_all_accounts,
  SUM(total_messages_sent) as total_messages_all_accounts,
  SUM(paid_messages_count) as total_paid_messages
FROM message_costs_weekly_by_account
WHERE week_start >= date_trunc('week', CURRENT_DATE - INTERVAL '4 weeks')::date
GROUP BY week_start, year, week_number
ORDER BY week_start DESC;
```

## Mise à jour des coûts

Pour mettre à jour les coûts des messages, vous pouvez utiliser :

```sql
-- Exemple : Mettre à jour le coût d'un message template (généralement 0.005 à 0.09 USD selon le pays)
UPDATE messages 
SET cost = 0.005, cost_currency = 'USD'
WHERE wa_message_id = 'votre-message-id'
  AND direction = 'outgoing'
  AND message_type = 'template';
```

## Notes importantes

- Les messages conversationnels (dans une fenêtre de 24h) sont généralement gratuits (cost = 0)
- Les messages template sont payants (coût variable selon le pays)
- Le coût par défaut est 0.0 USD
- L'index est optimisé pour les requêtes sur les messages sortants avec coût > 0

