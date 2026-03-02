# Sistema de Gestão — Kavalheiro Barbearia (v4)
Inclui:
- Agenda (dia/semana) + financeiro básico (se permitido)
- Agendamento online (estilo Calendly): clientes veem horários disponíveis e enviam pedido (status **Pendente**)
- Aprovação do barbeiro/admin para confirmar (vira **Agendado**)
- Bloquear horários/dias (folgas/intervalos) sem conflito
- Comissão **por serviço** (Service.commission_percent) com fallback para comissão do barbeiro (User.commission_percent)
- Regras de acesso por usuário (admin aprova barbeiros e permissões)

## Rodar local
```bash
cd Kavalheiro_Barbearia_Sistema_v4
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Acesse: http://localhost:5000

Login padrão (troque depois):
- admin / admin123
- barbeiro2 / barber123

## Como usar o agendamento online
Abra: `/book` (pode colocar no link da bio).
O cliente escolhe: barbeiro, serviço, data e horário disponível → envia pedido.
No sistema, use `/admin/pending` (admin) ou o barbeiro com permissão de aprovação para Aprovar/Rejeitar.

## Como bloquear folga/intervalo
Abra: `/blocks` e crie bloqueios por período.
Admin pode criar bloqueio geral (para todos) ou por barbeiro.
