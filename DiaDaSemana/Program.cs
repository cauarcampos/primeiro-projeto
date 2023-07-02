class Program
{
    static void Main()
    {
        Console.WriteLine("=== Conversor de Número para Dia da Semana ===");
        Console.Write("Digite um número de 1 a 7: ");
        int numero = int.Parse(Console.ReadLine());

        string diaSemana;

        switch (numero)
        {
            case 1:
                diaSemana = "Domingo";
                break;
            case 2:
                diaSemana = "Segunda-feira";
                break;
            case 3:
                diaSemana = "Terça-feira";
                break;
            case 4:
                diaSemana = "Quarta-feira";
                break;
            case 5:
                diaSemana = "Quinta-feira";
                break;
            case 6:
                diaSemana = "Sexta-feira";
                break;
            case 7:
                diaSemana = "Sábado";
                break;
            default:
                diaSemana = "Número inválido";
                break;
        }

        Console.WriteLine("O número " + numero + " corresponde a: " + diaSemana);

        Console.WriteLine("Pressione qualquer tecla para sair.");
        Console.ReadKey();
    }
}
