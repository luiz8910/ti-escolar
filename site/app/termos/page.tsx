import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { EMPRESA, PENDENTE, enderecoCompleto } from "@/lib/empresa";

/*
 * NOTA PARA A EQUIPE: texto-base redigido a partir do funcionamento real da
 * plataforma. Submeta à revisão jurídica antes de usar como instrumento
 * contratual — em especial as cláusulas de responsabilidade e rescisão.
 */

export const metadata: Metadata = {
  title: "Termos de Uso",
  description:
    "Condições de uso da plataforma TI-Escolar por escolas contratantes, suas equipes e responsáveis pelos alunos.",
};

export default function TermosPage() {
  const endereco = enderecoCompleto();

  return (
    <LegalPage
      title="Termos de Uso"
      intro={`Estas condições regem o uso da plataforma ${EMPRESA.nome} pelas escolas contratantes, por suas equipes e pelos responsáveis que se comunicam com a instituição através do serviço.`}
    >
      <h2>1. Quem presta o serviço</h2>
      <p>
        O <strong>{EMPRESA.nome}</strong> é operado por{" "}
        <strong>{EMPRESA.razaoSocial}</strong>
        {EMPRESA.cnpj !== PENDENTE && (
          <>
            , CNPJ nº <strong>{EMPRESA.cnpj}</strong>
          </>
        )}
        {endereco && <>, com endereço em {endereco}</>}, doravante &quot;nós&quot;. Contato:{" "}
        <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a>.
      </p>

      <h2>2. O que a plataforma faz</h2>
      <p>
        O {EMPRESA.nome} é um serviço de comunicação escolar que opera pelo WhatsApp e por
        um painel administrativo na web. Ele permite responder dúvidas de responsáveis,
        entregar documentos, enviar comunicados a turmas e organizar rotinas internas entre
        secretaria e professores.
      </p>
      <p>
        O serviço é acessório à gestão da escola: ele <strong>não substitui</strong> os
        registros oficiais da instituição nem os sistemas exigidos pela rede de ensino.
      </p>

      <h2>3. Quem pode usar</h2>
      <ul>
        <li>
          <strong>Escola contratante:</strong> pessoa jurídica ou órgão público que contrata
          o serviço e responde pelos dados que insere na plataforma.
        </li>
        <li>
          <strong>Equipe da escola:</strong> profissionais da secretaria, gestão e corpo
          docente, com acesso individual concedido pela escola.
        </li>
        <li>
          <strong>Responsáveis:</strong> pais e responsáveis legais que interagem pelo
          WhatsApp, sem necessidade de cadastro próprio.
        </li>
      </ul>

      <h2>4. Contas e credenciais</h2>
      <p>
        O acesso ao painel é pessoal e intransferível. A escola é responsável por conceder,
        revisar e revogar acessos da sua equipe, e cada usuário responde pelo sigilo da sua
        senha. Suspeita de uso indevido deve ser comunicada imediatamente para que o acesso
        seja bloqueado.
      </p>

      <h2>5. Responsabilidades da escola</h2>
      <ul>
        <li>
          Garantir que possui base legal para tratar os dados de alunos e responsáveis que
          insere na plataforma.
        </li>
        <li>
          Manter o cadastro atualizado — inclusive removendo contatos que não devem mais
          receber comunicados.
        </li>
        <li>
          Revisar o conteúdo que cadastra na base de conhecimento, já que é dele que saem as
          respostas automáticas.
        </li>
        <li>
          Usar o canal apenas para comunicação institucional, sem enviar publicidade de
          terceiros.
        </li>
        <li>Respeitar as políticas do WhatsApp Business e a legislação aplicável.</li>
      </ul>

      <h2>6. Uso proibido</h2>
      <p>É vedado utilizar a plataforma para:</p>
      <ul>
        <li>Enviar mensagens não solicitadas a quem não tem vínculo com a escola.</li>
        <li>Disparar conteúdo ilícito, discriminatório, difamatório ou enganoso.</li>
        <li>Tentar acessar dados de outra escola ou burlar controles de permissão.</li>
        <li>
          Sobrecarregar, sondar ou realizar engenharia reversa da infraestrutura do serviço.
        </li>
        <li>Comercializar ou sublicenciar o acesso a terceiros sem autorização escrita.</li>
      </ul>

      <h2>7. Respostas automáticas e limites da IA</h2>
      <p>
        As respostas ao responsável são geradas por um modelo de linguagem a partir dos
        documentos cadastrados pela escola, com citação da fonte. Ainda assim, respostas
        automáticas podem conter imprecisões.
      </p>
      <p>
        Informações que produzam efeito formal — matrícula, avaliação, situação financeira,
        decisão disciplinar — devem ser confirmadas pela secretaria. A escola é responsável
        pelo conteúdo que cadastra e, portanto, pelas respostas dele derivadas.
      </p>

      <h2>8. Dependência do WhatsApp</h2>
      <p>
        A entrega das mensagens depende da plataforma WhatsApp, operada pela Meta Platforms,
        Inc., que impõe regras próprias, limites diários de envio e exigências de
        aprovação de modelos de mensagem. Não respondemos por indisponibilidade,
        bloqueio, alteração de política ou limitação imposta por essa plataforma.
      </p>

      <h2>9. Contratação, valores e suspensão</h2>
      <p>
        Plano, ciclo de cobrança e valores constam da proposta comercial aceita pela escola.
        A falta de pagamento, após aviso, pode levar à suspensão do acesso ao painel e aos
        disparos, com registro do motivo. O acesso é restabelecido com a regularização.
      </p>

      <h2>10. Disponibilidade</h2>
      <p>
        Empregamos esforços razoáveis para manter o serviço disponível, mas ele pode ser
        interrompido para manutenção, atualização ou por falha de terceiros dos quais
        dependemos. Manutenções programadas são comunicadas com antecedência sempre que
        possível.
      </p>

      <h2>11. Propriedade intelectual</h2>
      <p>
        O software, a marca e a documentação do {EMPRESA.nome} são de nossa titularidade. O
        contrato concede à escola uma licença de uso, não exclusiva e intransferível, pelo
        período contratado. Os <strong>dados inseridos pela escola continuam sendo dela</strong>.
      </p>

      <h2>12. Proteção de dados</h2>
      <p>
        O tratamento de dados pessoais segue a{" "}
        <a href="/privacidade/">Política de Privacidade</a>, parte integrante destes
        termos. Nessa relação, a escola é controladora e nós somos operador.
      </p>

      <h2>13. Limitação de responsabilidade</h2>
      <p>
        Na máxima extensão permitida pela lei, não respondemos por danos indiretos, lucros
        cessantes ou perda de oportunidade decorrentes do uso do serviço, nem por conteúdo
        cadastrado pela escola ou por falha de plataformas de terceiros. Nossa
        responsabilidade, quando cabível, fica limitada ao valor pago pela escola nos 12
        meses anteriores ao evento.
      </p>

      <h2>14. Encerramento</h2>
      <p>
        Qualquer das partes pode encerrar a contratação na forma prevista na proposta
        comercial. Encerrado o serviço, a escola pode solicitar a exportação dos seus dados
        dentro do prazo acordado, após o qual eles são eliminados conforme a Política de
        Privacidade.
      </p>

      <h2>15. Alterações destes termos</h2>
      <p>
        Podemos atualizar estes termos para refletir mudanças no serviço ou na legislação.
        A data da última atualização fica no topo da página, e mudanças relevantes são
        comunicadas às escolas contratantes com antecedência razoável.
      </p>

      <h2>16. Lei aplicável e foro</h2>
      <p>
        Estes termos são regidos pelas leis brasileiras. Fica eleito o foro da comarca da
        sede da contratada para dirimir controvérsias, salvo hipótese de foro privilegiado
        prevista em lei.
      </p>

      <h2>17. Contato</h2>
      <p>
        Dúvidas sobre estes termos:{" "}
        <a href={`mailto:${EMPRESA.email}`}>{EMPRESA.email}</a>.
      </p>
    </LegalPage>
  );
}
