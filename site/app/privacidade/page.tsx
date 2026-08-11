import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { EMPRESA, PENDENTE, enderecoCompleto } from "@/lib/empresa";

/*
 * NOTA PARA A EQUIPE: este é um texto-base, redigido a partir do funcionamento
 * real da plataforma. Antes de tratar dados de alunos em produção, submeta-o à
 * revisão de um advogado — sobretudo os prazos de retenção e o papel de operador
 * perante cada escola contratante.
 */

export const metadata: Metadata = {
  title: "Política de Privacidade",
  description:
    "Como o TI-Escolar coleta, usa, compartilha e protege os dados pessoais tratados na plataforma, conforme a LGPD.",
};

export default function PrivacidadePage() {
  const endereco = enderecoCompleto();

  return (
    <LegalPage
      title="Política de Privacidade"
      intro={`Esta política explica como o ${EMPRESA.nome} trata dados pessoais na prestação do serviço de comunicação escolar, em conformidade com a Lei Geral de Proteção de Dados (Lei nº 13.709/2018).`}
    >
      <h2>1. Quem somos</h2>
      <p>
        O <strong>{EMPRESA.nome}</strong> é um serviço operado por{" "}
        <strong>{EMPRESA.razaoSocial}</strong>
        {EMPRESA.cnpj !== PENDENTE && (
          <>
            , inscrita no CNPJ sob o nº <strong>{EMPRESA.cnpj}</strong>
          </>
        )}
        {endereco && <>, com endereço em {endereco}</>}. Para qualquer assunto relativo a
        dados pessoais, o contato é <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a>.
      </p>

      <h2>2. Nosso papel: operador, não controlador</h2>
      <p>
        A escola contratante decide quais dados são tratados e para qual finalidade — ela é
        a <strong>controladora</strong>. O {EMPRESA.nome} atua como{" "}
        <strong>operador</strong>, tratando os dados apenas conforme as instruções da
        escola e o contrato firmado.
      </p>
      <p>
        Na prática: se você é responsável por um aluno e quer saber por que a escola guarda
        determinado dado, ou quer corrigi-lo ou excluí-lo, o pedido deve ser dirigido
        primeiro à escola. Nós apoiamos a escola no atendimento desses pedidos.
      </p>

      <h2>3. Dados que tratamos</h2>
      <h3>3.1. Responsáveis e alunos</h3>
      <ul>
        <li>
          <strong>Identificação e contato:</strong> nome do responsável, número de WhatsApp
          e, quando cadastrado pela escola, e-mail.
        </li>
        <li>
          <strong>Vínculo escolar:</strong> nome do aluno, turma/série, matrícula e a
          relação entre aluno e responsável.
        </li>
        <li>
          <strong>Conteúdo das conversas:</strong> as mensagens trocadas com o canal oficial
          da escola no WhatsApp, incluindo as respostas enviadas pela plataforma e os
          documentos anexados.
        </li>
        <li>
          <strong>Dados da ficha de matrícula:</strong> quando a escola usa a matrícula
          digital, os campos exigidos pela rede de ensino — que podem incluir dados
          sensíveis, como cor/raça, condição de saúde, deficiência, laudo e restrição
          alimentar.
        </li>
        <li>
          <strong>Arquivos enviados pelo responsável:</strong> fotos e documentos que o
          próprio responsável envia ao canal da escola no WhatsApp — como atestado médico,
          documento de identidade, certidão, comprovante de residência e comprovante de
          pagamento. Podem conter dados sensíveis, especialmente de saúde. Esses arquivos
          têm <strong>prazo de guarda definido</strong> e são apagados automaticamente ao
          fim dele; enquanto existem, só podem ser abertos por profissionais autenticados
          da própria escola, e todo acesso fica registrado.
        </li>
        <li>
          <strong>Status de entrega:</strong> se um aviso enviado foi entregue ou lido.
        </li>
      </ul>

      <h3>3.2. Funcionários da escola</h3>
      <ul>
        <li>Nome, e-mail e telefone de profissionais da secretaria e do corpo docente.</li>
        <li>Credenciais de acesso ao painel, armazenadas apenas como resumo criptográfico.</li>
        <li>Registro das ações realizadas no painel, para fins de auditoria.</li>
      </ul>

      <h2>4. Dados de crianças e adolescentes</h2>
      <p>
        A plataforma trata dados de crianças e adolescentes no interesse deles, para
        viabilizar a comunicação entre a escola e quem é legalmente responsável. Esses dados
        são fornecidos pela escola no âmbito da relação educacional e nunca são usados para
        publicidade, perfilamento comercial ou qualquer finalidade alheia à comunicação
        escolar.
      </p>

      <h2>5. Para que usamos</h2>
      <ul>
        <li>Responder dúvidas dos responsáveis sobre procedimentos e avisos da escola.</li>
        <li>Entregar documentos solicitados, como declarações, boletins e calendários.</li>
        <li>Enviar comunicados e avisos institucionais autorizados pela escola.</li>
        <li>Organizar a rotina interna entre secretaria e professores.</li>
        <li>Manter histórico e registro de auditoria, para prestação de contas da escola.</li>
        <li>Garantir a segurança do serviço e prevenir uso indevido.</li>
      </ul>
      <p>
        As bases legais são a <strong>execução de contrato</strong> com a escola, o{" "}
        <strong>cumprimento de obrigação legal ou regulatória</strong> da instituição de
        ensino e o <strong>legítimo interesse</strong> na segurança da plataforma.
      </p>

      <h2>6. Inteligência artificial</h2>
      <p>
        As respostas automáticas são geradas por um modelo de linguagem a partir dos
        documentos que a própria escola cadastra, e a resposta cita a fonte usada. Alguns
        recursos, como a leitura de fichas e a importação de listas de alunos, também
        submetem o conteúdo enviado a esse processamento.
      </p>
      <p>
        O conteúdo enviado ao provedor de IA é usado <strong>apenas</strong> para gerar a
        resposta daquela solicitação. Não autorizamos o uso desses dados para treinamento de
        modelos. Nenhuma decisão com efeito jurídico sobre o aluno é tomada
        automaticamente: o assistente informa, quem decide é a escola.
      </p>

      <h2>7. Com quem compartilhamos</h2>
      <p>
        Não vendemos dados pessoais. O compartilhamento se limita ao necessário para o
        serviço funcionar:
      </p>
      <ul>
        <li>
          <strong>Plataforma de mensageria (WhatsApp):</strong> a entrega das mensagens
          depende da infraestrutura do WhatsApp e do provedor de envio contratado.
        </li>
        <li>
          <strong>Provedor de inteligência artificial:</strong> recebe o conteúdo necessário
          para gerar a resposta, conforme a seção 6.
        </li>
        <li>
          <strong>Infraestrutura de nuvem:</strong> hospedagem da aplicação e do banco de
          dados.
        </li>
        <li>
          <strong>Autoridades:</strong> quando houver determinação legal ou judicial.
        </li>
      </ul>

      <h2>8. Isolamento entre escolas</h2>
      <p>
        A plataforma é multi-instituição, mas cada escola tem seu próprio ambiente isolado.
        Toda consulta é delimitada pela escola de origem: dados de uma instituição não são
        acessíveis a outra, em nenhuma tela ou relatório.
      </p>

      <h2>9. Por quanto tempo guardamos</h2>
      <p>
        Os dados são mantidos enquanto durar o contrato com a escola e pelo prazo que a
        legislação educacional exigir da instituição. Encerrado o contrato, os dados são
        eliminados ou devolvidos à escola conforme ela determinar, ressalvado o que
        precisarmos reter para cumprir obrigação legal ou exercer direitos em processo.
      </p>
      <p>
        Os <strong>arquivos enviados pelos responsáveis pelo WhatsApp</strong> (item 3.1)
        têm prazo próprio e mais curto, por conterem dados sensíveis: são apagados
        automaticamente após o período de guarda definido com a escola, sem depender de
        pedido. O prazo padrão é de <strong>12 meses</strong>, o que cobre o ciclo letivo
        em que o documento foi entregue.
      </p>

      <h2>10. Segurança</h2>
      <ul>
        <li>Tráfego criptografado em trânsito (HTTPS).</li>
        <li>Acesso ao painel por autenticação individual, com sessão expirável.</li>
        <li>Senhas armazenadas apenas como resumo criptográfico, nunca em texto puro.</li>
        <li>Perfis de permissão distintos para secretaria e professores.</li>
        <li>Registro de auditoria das ações realizadas no painel.</li>
      </ul>
      <p>
        Nenhum sistema é imune a incidentes. Havendo um incidente de segurança relevante,
        comunicamos a escola contratante e apoiamos as notificações exigidas pela LGPD.
      </p>

      <h2>11. Seus direitos</h2>
      <p>
        A LGPD garante ao titular o direito de confirmar a existência de tratamento, acessar
        seus dados, corrigir dados incompletos ou desatualizados, solicitar anonimização,
        bloqueio ou eliminação, pedir portabilidade, obter informação sobre
        compartilhamentos e revogar consentimento.
      </p>
      <p>
        Como atuamos na condição de operador, encaminhe o pedido primeiro à{" "}
        <strong>escola</strong>. Se preferir, escreva para{" "}
        <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a> e nós direcionamos a
        solicitação à instituição responsável.
      </p>

      <h2>12. Como parar de receber mensagens</h2>
      <p>
        Você pode pedir a interrupção dos envios a qualquer momento, respondendo à própria
        conversa no WhatsApp ou avisando a secretaria da escola. Vale registrar que alguns
        comunicados são obrigações da instituição de ensino perante o responsável legal, e a
        escola pode precisar mantê-los por outro meio.
      </p>

      <h2>13. Alterações desta política</h2>
      <p>
        Podemos atualizar este documento para refletir mudanças no serviço ou na legislação.
        A data da última atualização fica sempre no topo da página; mudanças relevantes são
        comunicadas às escolas contratantes.
      </p>

      <h2>14. Contato</h2>
      <p>
        Dúvidas, solicitações ou reclamações sobre privacidade:{" "}
        <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a>.
      </p>
    </LegalPage>
  );
}
