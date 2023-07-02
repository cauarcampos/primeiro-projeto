class Program
{
    static void Main()
    {
        Console.WriteLine("=== Par ou Ímpar ===");
        Console.Write("Digite um número: ");
        int numero = int.Parse(Console.ReadLine());

        if (numero % 2 == 0)
        {
            Console.WriteLine(numero + " é um número par.");
        }
        else
        {
            Console.WriteLine(numero + " é um número ímpar.");
        }

        Console.WriteLine("Pressione qualquer tecla para sair.");
        Console.ReadKey();
    }
}

