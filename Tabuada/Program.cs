class Program
{
    static void Main()
    {
        Console.WriteLine("=== Tabuada ===");
        Console.Write("Digite um número: ");
        int numero = int.Parse(Console.ReadLine());

        Console.WriteLine("Tabuada do " + numero + ":");
        for (int i = 1; i <= 10; i++)
        {
            int resultado = numero * i;
            Console.WriteLine(numero + " x " + i + " = " + resultado);
        }

        Console.WriteLine("Pressione qualquer tecla para sair.");
        Console.ReadKey();
    }
}
